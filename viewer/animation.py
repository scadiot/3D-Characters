"""Clips d'animation indexés par nom de bone canonique."""
from dataclasses import dataclass

import numpy as np

from viewer.mathutil import slerp
from viewer.skeleton import Pose, Skeleton


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
    hips_rest_t: np.ndarray | None  # translation locale de repos des Hips dans le fichier d'animation

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


def hips_ratio(skeleton: Skeleton, clip: AnimationClip) -> float:
    """Rapport d'échelle entre les Hips de repos du modèle et celles de l'animation (cm/m)."""
    i = skeleton.index("Hips")
    if i is None or clip.hips_rest_t is None:
        return 1.0
    anim_length = np.linalg.norm(clip.hips_rest_t)
    return float(np.linalg.norm(skeleton.rest_t[i]) / anim_length) if anim_length > 1e-8 else 1.0


def apply_clip(clip: AnimationClip, skeleton: Skeleton, pose: Pose, t: float, ratio: float) -> None:
    """Écrit dans `pose` : rotations de tous les bones appariés, translation des Hips seulement."""
    for name, track in clip.rotations.items():
        i = skeleton.index(name)
        if i is not None:
            pose.r[i] = sample_track(track, t)
    hips_track = clip.translations.get("Hips")
    i = skeleton.index("Hips")
    if hips_track is not None and i is not None:
        pose.t[i] = sample_track(hips_track, t) * ratio
