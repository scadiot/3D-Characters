"""Génère un enfant low poly sur squelette Mixamo : sample/Characters/Child/Child.glb.

Même construction que l'humain (build_human.py), puis les proportions sont changées par une déformation
appliquée aux triangles et au squelette : jambes et torse raccourcis, silhouette plus trapue,
bras plus courts, et une tête bien moins réduite que le corps, donc proportionnellement plus grosse.
Les zones de raccord (cou, épaules) passent en douceur d'une transformation à l'autre.

    python tools/build_child.py [chemin_sortie.glb]
"""
import sys
from pathlib import Path

import numpy as np

from build_human import COLORS, generate

# repères du modèle adulte
_HIP_Y, _CHIN_Y, _ARM_Y, _ARM_ROOT = 0.93, 1.53, 1.43, 0.15

LEG = 0.50        # échelle verticale des jambes
TORSO = 0.80      # échelle verticale du torse et du cou
WIDTH = 0.72      # largeur et profondeur du corps
HEAD = 0.95       # échelle uniforme de la tête (cheveux et oreilles compris)
ARM_LENGTH = 0.60
ARM_THICKNESS = 0.72
EYES = 1.3        # yeux plus grands dans la texture du visage


def _smoothstep(a: float, b: float, x: float) -> float:
    t = float(np.clip((x - a) / (b - a), 0, 1))
    return t * t * (3 - 2 * t)


def _height(y: float) -> float:
    """Hauteur dans le corps de l'enfant d'un point du corps adulte."""
    return y * LEG if y <= _HIP_Y else _HIP_Y * LEG + (y - _HIP_Y) * TORSO


def warp(p: np.ndarray) -> np.ndarray:
    x, y, z = p
    body = np.array([x * WIDTH, _height(y), z * WIDTH])
    side = np.sign(x) or 1.0
    arm = np.array([side * (_ARM_ROOT * WIDTH + (abs(x) - _ARM_ROOT) * ARM_LENGTH),
                    _height(_ARM_Y) + (y - _ARM_Y) * ARM_THICKNESS, z * ARM_THICKNESS])
    head = np.array([0, _height(_CHIN_Y), 0]) + (p - (0, _CHIN_Y, 0)) * HEAD
    to_arm = _smoothstep(0.11, 0.22, abs(x)) * _smoothstep(1.28, 1.36, y)
    to_head = _smoothstep(1.46, 1.54, y) * (1 - _smoothstep(0.17, 0.22, abs(x)))
    mixed = body + (arm - body) * to_arm
    return mixed + (head - mixed) * to_head


COLORS_CHILD = {**COLORS,
                "hair": (0.50, 0.30, 0.13, 1),
                "shirt": (0.96, 0.55, 0.16, 1),
                "jeans": (0.32, 0.47, 0.72, 1),
                "shoe": (0.82, 0.20, 0.16, 1),
                "iris": (0.36, 0.24, 0.12, 1)}

SKINS_CHILD = {
    "blond_vert": {"hair": (0.88, 0.72, 0.40, 1), "shirt": (0.30, 0.68, 0.36, 1), "iris": (0.28, 0.50, 0.78, 1),
                   "shoe": (0.20, 0.30, 0.65, 1)},
    "brune_rose": {"hair": (0.12, 0.08, 0.06, 1), "shirt": (0.92, 0.48, 0.64, 1), "jeans": (0.48, 0.44, 0.62, 1),
                   "shoe": (0.95, 0.95, 0.95, 1)},
    "roux_bleu": {"skin": (0.97, 0.82, 0.72, 1), "hair": (0.78, 0.33, 0.10, 1), "shirt": (0.45, 0.70, 0.92, 1),
                  "iris": (0.30, 0.55, 0.32, 1)},
    "metisse_jaune": {"skin": (0.66, 0.46, 0.32, 1), "hair": (0.08, 0.06, 0.05, 1), "shirt": (0.98, 0.84, 0.25, 1),
                      "mouth": (0.50, 0.28, 0.24, 1), "iris": (0.20, 0.12, 0.07, 1)},
}


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "sample/Characters/Child/Child.glb"
    generate(out, "Child", COLORS_CHILD, SKINS_CHILD, warp=warp, eyes=EYES)
