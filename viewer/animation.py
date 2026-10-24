"""Clips d'animation indexés par nom de bone canonique."""
from dataclasses import dataclass

import numpy as np

from viewer.mathutil import mat3_to_quat, slerp, trs_to_mat4
from viewer.skeleton import Pose, Skeleton, yaw_matrix


@dataclass
class Track:
    times: np.ndarray        # (K,)
    values: np.ndarray       # (K, 3) translation ou (K, 4) rotation
    interpolation: str       # "LINEAR" | "STEP"


@dataclass
class AnimationClip:
    name: str
    duration: float
    rotations: dict[str, Track]
    translations: dict[str, Track]
    skeleton: Skeleton  # squelette du fichier d'animation (sa pose de repos sert de référence)

    def track_names(self) -> set[str]:
        return set(self.rotations) | set(self.translations)


def loop_time(t: float, duration: float) -> float:
    return float(t % duration) if duration > 0 else 0.0


def sample_track(track: Track, t: float) -> np.ndarray:
    times, values = track.times, track.values
    if t <= times[0]:
        return values[0].copy()
    if t >= times[-1]:
        return values[-1].copy()
    k = int(np.searchsorted(times, t, side="right")) - 1
    if track.interpolation == "STEP":
        return values[k].copy()
    u = (t - times[k]) / (times[k + 1] - times[k])
    if values.shape[1] == 4:
        return slerp(values[k], values[k + 1], u)
    return values[k] + u * (values[k + 1] - values[k])


def sample_pose(clip: AnimationClip, t: float) -> Pose:
    """Pose du squelette source du clip à l'instant t (toutes les pistes appliquées)."""
    sk = clip.skeleton
    pose = sk.rest_pose()
    for tracks, values in ((clip.rotations, pose.r), (clip.translations, pose.t)):
        for name, track in tracks.items():
            i = sk.index(name)
            if i is not None:
                values[i] = sample_track(track, t)
    return pose


def _rotations(globals_: np.ndarray) -> np.ndarray:
    """Partie rotation de matrices globales (échelle retirée)."""
    m = globals_[..., :3, :3]
    return m / np.linalg.norm(m, axis=-2, keepdims=True)


class Retargeter:
    """Transfère un clip sur un autre squelette en espace monde.

    Pour chaque bone apparié par nom, la variation de rotation monde par rapport à la
    T-pose source est appliquée à la T-pose du modèle : les axes locaux des deux rigs
    peuvent différer (export Blender, etc.) tant que leurs poses de repos coïncident.
    Un écart d'orientation (perso regardant -Z au lieu de +Z) est compensé en exprimant
    les variations source dans le repère du modèle.
    La position des Hips suit le déplacement source, mis à l'échelle de leur hauteur.
    """

    def __init__(self, model: Skeleton, clip: AnimationClip):
        self.model, self.clip = model, clip
        source = clip.skeleton
        self.pairs = {}
        for name in clip.rotations:
            i, j = model.index(name), source.index(name)
            if i is not None and j is not None:
                self.pairs[i] = j
        model_rest = model.global_matrices(model.rest_pose())
        source_rest = source.global_matrices(source.rest_pose())
        self.model_rest_r = _rotations(model_rest)
        self.source_rest_r = _rotations(source_rest)
        self.align = yaw_matrix(model.facing_yaw() - source.facing_yaw())[:3, :3]
        self.hips = model.index("Hips")
        self.source_hips = source.index("Hips") if "Hips" in clip.translations else None
        self.ratio = 1.0
        if self.hips is not None and self.source_hips is not None:
            self.model_hips_rest = model_rest[self.hips][:3, 3]
            self.source_hips_rest = source_rest[self.source_hips][:3, 3]
            if abs(self.source_hips_rest[1]) > 1e-8:
                self.ratio = float(self.model_hips_rest[1] / self.source_hips_rest[1])
        else:
            self.source_hips = None

    def pose(self, t: float) -> Pose:
        source_globals = self.clip.skeleton.global_matrices(sample_pose(self.clip, t))
        source_r = _rotations(source_globals)
        sk = self.model
        pose = sk.rest_pose()
        globals_ = np.empty((len(sk.names), 4, 4))
        for i in sk.order:
            p = sk.parents[i]
            parent = globals_[p] if p >= 0 else np.eye(4)
            j = self.pairs.get(i)
            if j is not None:
                delta = self.align @ source_r[j] @ self.source_rest_r[j].T @ self.align.T
                target = delta @ self.model_rest_r[i]
                parent_r = _rotations(parent)
                pose.r[i] = mat3_to_quat(parent_r.T @ target)
            if i == self.hips and self.source_hips is not None:
                offset = source_globals[self.source_hips][:3, 3] - self.source_hips_rest
                world = np.append(self.model_hips_rest + self.align @ offset * self.ratio, 1.0)
                pose.t[i] = (np.linalg.inv(parent) @ world)[:3]
            globals_[i] = parent @ trs_to_mat4(pose.t[i:i + 1], pose.r[i:i + 1], pose.s[i:i + 1])[0]
        return pose
