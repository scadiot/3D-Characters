"""Clips d'animation indexés par nom de bone canonique."""
from dataclasses import dataclass

import numpy as np


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
