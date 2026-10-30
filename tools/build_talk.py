"""Génère l'animation « talk » (personnage qui parle) : sample/Animations/talk.glb.

Le rig Mixamo n'a pas de mâchoire : la parole passe par le langage corporel. Des gestes
(hochements de tête, mains qui montent et battent la mesure, buste qui accompagne) sont
superposés à la respiration de idle.glb, rejouée deux fois pour que la boucle reste continue.

    python tools/build_talk.py [chemin_sortie.glb]
"""
import sys
from pathlib import Path

import numpy as np
from pygltflib import (GLTF2, Accessor, Animation, AnimationChannel, AnimationChannelTarget,
                       AnimationSampler, Asset, Buffer, BufferView, Node, Scene)

from viewer.animation import sample_pose
from viewer.gltf_loader import load_glb
from viewer.mathutil import axis_angle_quat, mat3_to_quat, quat_to_mat3

ROOT = Path(__file__).resolve().parent.parent
IDLE = ROOT / "sample/Animations/idle.glb"
DURATION = 5.0  # deux cycles de idle (2,5 s)
FPS = 30
UP = np.array([0.0, 1.0, 0.0])
FORWARD = np.array([0.0, 0.0, 1.0])  # idle regarde +Z


def _wave(t: float, k: int, phase: float = 0.0) -> float:
    """Sinusoïde de k périodes sur la durée du clip : la boucle reste continue."""
    return float(np.sin(2 * np.pi * k * t / DURATION + phase))


def _bump(t: float, start: float, end: float, ramp: float = 0.45) -> float:
    """0 hors de [start, end], 1 au milieu, montée et descente lissées sur `ramp` secondes."""
    def smooth(x: float) -> float:
        x = min(max(x, 0.0), 1.0)
        return x * x * (3 - 2 * x)
    return smooth((t - start) / ramp) * smooth((end - t) / ramp)


# Plages de geste de chaque main (secondes) : elles alternent et se chevauchent un peu.
_RIGHT_GESTURES = [(0.2, 2.1), (3.3, 4.8)]
_LEFT_GESTURES = [(1.5, 3.6)]


def _envelope(t: float, ranges) -> float:
    return max(_bump(t, a, b) for a, b in ranges)


def _rotations(t: float, direction) -> list[tuple[str, np.ndarray, float]]:
    """(bone, axe monde, angle) des gestes à l'instant t.

    `direction(bone, enfant)` donne l'axe monde du bone vers cet enfant dans la pose idle.
    """
    out = [
        ("Head", np.array([1.0, 0, 0]), np.radians(5) * (0.6 * _wave(t, 9) + 0.4 * _wave(t, 14, 1.0))),
        ("Head", UP, np.radians(7) * _wave(t, 2, 0.3)),
        ("Head", FORWARD, np.radians(3) * _wave(t, 3, 1.2)),
        ("Neck", UP, np.radians(3) * _wave(t, 2, 0.3)),
        ("Spine2", UP, np.radians(4) * _wave(t, 1, 0.8)),
        ("Spine2", np.array([1.0, 0, 0]), np.radians(2) * _wave(t, 5)),
    ]
    for side, sign, ranges, amount in (("Right", 1.0, _RIGHT_GESTURES, 1.0), ("Left", -1.0, _LEFT_GESTURES, 0.8)):
        e = _envelope(t, ranges) * amount
        if e <= 0:
            continue
        arm, fore, hand = (direction(f"{side}{a}", f"{side}{b}")
                           for a, b in (("Arm", "ForeArm"), ("ForeArm", "Hand"), ("Hand", "HandMiddle1")))
        outward = np.array([-sign, 0.0, 0.0])  # le côté droit est en -X
        # Coude légèrement avancé, près du corps.
        out.append((f"{side}Arm", _unit(np.cross(arm, FORWARD)), np.radians(15) * e))
        # Avant-bras relevé devant, main ouverte vers l'extérieur, avec des battements pendant la phrase.
        beat = np.radians(10) * _wave(t, 12, 0.5 if side == "Right" else 2.0)
        lift = _unit(FORWARD + 0.6 * UP + 0.7 * outward)
        out.append((f"{side}ForeArm", _unit(np.cross(fore, lift)), (np.radians(85) + beat) * e))
        # Main tournée paume vers le haut.
        out.append((f"{side}Hand", hand, -sign * np.radians(50) * e))
    return out


def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


def _rotation_part(m: np.ndarray) -> np.ndarray:
    r = m[:3, :3]
    return r / np.linalg.norm(r, axis=0, keepdims=True)


def build_tracks():
    idle = load_glb(IDLE)
    clip, sk = idle.clips[0], idle.skeleton
    rest_globals = sk.global_matrices(sample_pose(clip, 0.0))

    def direction(name: str, child: str) -> np.ndarray:
        return _unit(rest_globals[sk.index(child)][:3, 3] - rest_globals[sk.index(name)][:3, 3])

    times = np.arange(int(DURATION * FPS) + 1) / FPS
    rotations = {name: np.empty((len(times), 4)) for name in clip.rotations}
    translations = {name: np.empty((len(times), 3)) for name in clip.translations}
    for k, t in enumerate(times):
        pose = sample_pose(clip, t % clip.duration)
        g = sk.global_matrices(pose)
        for name, axis, angle in _rotations(t, direction):
            # Rotation exprimée dans le repère monde de la pose idle, autour de l'articulation.
            i = sk.index(name)
            world = _rotation_part(g[i])
            delta = world.T @ quat_to_mat3(axis_angle_quat(axis, angle)) @ world
            pose.r[i] = mat3_to_quat(quat_to_mat3(pose.r[i]) @ delta)
        for name, values in rotations.items():
            q = pose.r[sk.index(name)]
            values[k] = -q if k and np.dot(q, values[k - 1]) < 0 else q
        for name, values in translations.items():
            values[k] = pose.t[sk.index(name)]
    return idle, times, rotations, translations


def export(path: Path) -> None:
    idle, times, rotations, translations = build_tracks()
    source = GLTF2().load(str(IDLE))
    gltf = GLTF2(asset=Asset(generator="tools/build_talk.py"), scene=0, scenes=[Scene(nodes=source.scenes[0].nodes)])
    gltf.nodes = [Node(name=n.name, children=n.children or [], translation=n.translation,
                       rotation=n.rotation, scale=n.scale) for n in source.nodes]
    blob = bytearray()

    def accessor(arr: np.ndarray, kind: str, minmax: bool = False) -> int:
        data = np.ascontiguousarray(arr, np.float32).tobytes()
        gltf.bufferViews.append(BufferView(buffer=0, byteOffset=len(blob), byteLength=len(data)))
        blob.extend(data)
        gltf.accessors.append(Accessor(bufferView=len(gltf.bufferViews) - 1, componentType=5126, count=len(arr),
                                       type=kind, min=[float(arr.min())] if minmax else None,
                                       max=[float(arr.max())] if minmax else None))
        return len(gltf.accessors) - 1

    node_of = {name: idle.skeleton.index(name) for name in (*rotations, *translations)}
    anim = Animation(name="talk")
    time_accessor = accessor(times, "SCALAR", minmax=True)
    for tracks, kind, target in ((rotations, "VEC4", "rotation"), (translations, "VEC3", "translation")):
        for name, values in tracks.items():
            anim.samplers.append(AnimationSampler(input=time_accessor, output=accessor(values, kind),
                                                  interpolation="LINEAR"))
            anim.channels.append(AnimationChannel(sampler=len(anim.samplers) - 1,
                                                  target=AnimationChannelTarget(node=node_of[name], path=target)))
    gltf.animations = [anim]
    gltf.buffers = [Buffer(byteLength=len(blob))]
    gltf.set_binary_blob(bytes(blob))
    gltf.save_binary(str(path))


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "sample/Animations/talk.glb"
    export(out)
    print(f"Écrit : {out}")
