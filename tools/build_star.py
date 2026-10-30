"""Génère la pose « star » (bras et jambes tendus en étoile) : sample/Animations/star_pose.glb.

Part de TPose.glb : les bras, déjà tendus à l'horizontale, montent en diagonale et les jambes,
restées tendues, s'écartent. Les pieds sont redressés pour rester à plat et le bassin descend
pour qu'ils touchent toujours le sol. Les paumes sont tournées vers la caméra (+Z). Clip statique, comme sad_pose.glb.

    python -m tools.build_star [chemin_sortie.glb]
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
TPOSE = ROOT / "sample/Animations/TPose.glb"
TIMES = np.array([0.0, 1 / 15])  # même durée que les autres poses statiques
FORWARD = np.array([0.0, 0.0, 1.0])  # la T-pose regarde +Z, sa gauche est en +X
ARM_RAISE = np.radians(40)  # au-dessus de l'horizontale
LEG_SPREAD = np.radians(22)  # écart de chaque jambe par rapport à la verticale

# (bone, angle autour de l'axe avant) : un angle positif fait tourner +X vers +Y.
_ROTATIONS = [
    ("LeftArm", ARM_RAISE), ("RightArm", -ARM_RAISE),
    ("LeftUpLeg", LEG_SPREAD), ("RightUpLeg", -LEG_SPREAD),
    ("LeftFoot", -LEG_SPREAD), ("RightFoot", LEG_SPREAD),
]


def _rotation_part(m: np.ndarray) -> np.ndarray:
    r = m[:3, :3]
    return r / np.linalg.norm(r, axis=0, keepdims=True)


def _rotate(pose, sk, name: str, axis: np.ndarray, angle: float) -> None:
    """Tourne le bone autour de son articulation, d'un angle exprimé dans le repère monde."""
    i = sk.index(name)
    world = _rotation_part(sk.global_matrices(pose)[i])
    delta = world.T @ quat_to_mat3(axis_angle_quat(axis, angle)) @ world
    pose.r[i] = mat3_to_quat(quat_to_mat3(pose.r[i]) @ delta)


def _face_palm_forward(pose, sk, side: str, sign: float) -> None:
    """Tourne l'avant-bras et la main autour de l'axe du bras pour que la paume regarde la caméra."""
    g = sk.global_matrices(pose)
    pos = lambda n: g[sk.index(f"{side}{n}")][:3, 3]
    along = pos("HandMiddle1") - pos("Hand")
    along /= np.linalg.norm(along)
    # Normale de paume : main gauche et main droite sont en miroir.
    palm = sign * np.cross(along, pos("HandIndex1") - pos("HandPinky1"))
    target = FORWARD - np.dot(FORWARD, along) * along
    angle = np.arctan2(np.dot(along, np.cross(palm, target)), np.dot(palm, target))
    # Torsion partagée entre avant-bras et poignet, faute d'os de torsion dans le rig.
    for bone in ("ForeArm", "Hand"):
        _rotate(pose, sk, f"{side}{bone}", along, angle / 2)


def build_pose():
    tpose = load_glb(TPOSE)
    clip, sk = tpose.clips[0], tpose.skeleton
    pose = sample_pose(clip, 0.0)
    g = sk.global_matrices(pose)
    for name, angle in _ROTATIONS:
        # Rotation exprimée dans le repère monde de la T-pose, autour de l'articulation.
        i = sk.index(name)
        world = _rotation_part(g[i])
        delta = world.T @ quat_to_mat3(axis_angle_quat(FORWARD, angle)) @ world
        pose.r[i] = mat3_to_quat(quat_to_mat3(pose.r[i]) @ delta)
    _face_palm_forward(pose, sk, "Left", 1.0)
    _face_palm_forward(pose, sk, "Right", -1.0)

    # Jambes écartées = pieds plus hauts : le bassin descend d'autant.
    hip, foot = (g[sk.index(n)][:3, 3] for n in ("LeftUpLeg", "LeftFoot"))
    drop = (hip[1] - foot[1]) * (1 - np.cos(LEG_SPREAD))
    hips = sk.index("Hips")
    parent = np.linalg.inv(g[sk.parents[hips]]) if sk.parents[hips] >= 0 else np.eye(4)
    pose.t[hips] = pose.t[hips] + (parent[:3, :3] @ np.array([0.0, -drop, 0.0]))
    return tpose, clip, pose


def export(path: Path) -> None:
    tpose, clip, pose = build_pose()
    sk = tpose.skeleton
    source = GLTF2().load(str(TPOSE))
    gltf = GLTF2(asset=Asset(generator="tools/build_star.py"), scene=0, scenes=[Scene(nodes=source.scenes[0].nodes)])
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

    anim = Animation(name="star_pose")
    time_accessor = accessor(TIMES, "SCALAR", minmax=True)
    for names, values, kind, target in ((clip.rotations, pose.r, "VEC4", "rotation"),
                                        (clip.translations, pose.t, "VEC3", "translation")):
        for name in names:
            i = sk.index(name)
            anim.samplers.append(AnimationSampler(input=time_accessor, output=accessor(np.tile(values[i], (2, 1)), kind),
                                                  interpolation="LINEAR"))
            anim.channels.append(AnimationChannel(sampler=len(anim.samplers) - 1,
                                                  target=AnimationChannelTarget(node=i, path=target)))
    gltf.animations = [anim]
    gltf.buffers = [Buffer(byteLength=len(blob))]
    gltf.set_binary_blob(bytes(blob))
    gltf.save_binary(str(path))


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "sample/Animations/star_pose.glb"
    export(out)
    print(f"Écrit : {out}")
