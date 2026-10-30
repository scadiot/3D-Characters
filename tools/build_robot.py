"""Génère un robot low poly sur squelette Mixamo : sample/Characters/Robot/Robot.glb.

Chaque pièce est rigidement liée à un seul bone.

    python tools/build_robot.py [chemin_sortie.glb]
"""
import sys
from pathlib import Path

from lowpoly import Part, Rig, ball, box, export, prism

# (nom, parent, position monde en T-pose)
_CENTER = [
    ("Hips", None, (0, 0.95, 0)),
    ("Spine", "Hips", (0, 1.05, 0)),
    ("Spine1", "Spine", (0, 1.16, 0)),
    ("Spine2", "Spine1", (0, 1.27, 0)),
    ("Neck", "Spine2", (0, 1.45, 0)),
    ("Head", "Neck", (0, 1.53, 0)),
    ("HeadTop_End", "Head", (0, 1.80, 0)),
]


def _side(s: str, x: float) -> list:
    return [
        (f"{s}Shoulder", "Spine2", (0.06 * x, 1.40, 0)),
        (f"{s}Arm", f"{s}Shoulder", (0.19 * x, 1.40, 0)),
        (f"{s}ForeArm", f"{s}Arm", (0.44 * x, 1.40, 0)),
        (f"{s}Hand", f"{s}ForeArm", (0.67 * x, 1.40, 0)),
        (f"{s}UpLeg", "Hips", (0.10 * x, 0.90, 0)),
        (f"{s}Leg", f"{s}UpLeg", (0.10 * x, 0.50, 0)),
        (f"{s}Foot", f"{s}Leg", (0.10 * x, 0.10, 0)),
        (f"{s}ToeBase", f"{s}Foot", (0.10 * x, 0.03, 0.12)),
        (f"{s}Toe_End", f"{s}ToeBase", (0.10 * x, 0.03, 0.20)),
    ]


RIG = Rig(_CENTER + _side("Left", 1) + _side("Right", -1))

COLORS = {
    "white": (0.88, 0.89, 0.91, 1),
    "dark": (0.16, 0.17, 0.20, 1),
    "accent": (0.95, 0.45, 0.10, 1),
    "visor": (0.05, 0.08, 0.15, 1),
    "glow": (0.20, 0.90, 1.00, 1),
}


def build_body() -> Part:
    p = Part(RIG, COLORS)
    w = RIG.world
    # Bassin et torse
    box(p, "dark", "Hips", (0, 0.93, 0), (0.30, 0.14, 0.18), taper=(1.05, 1.0))
    box(p, "accent", "Hips", (0, 1.01, 0), (0.24, 0.03, 0.15))
    prism(p, "dark", "Spine", (0, 1.02, 0), (0, 1.17, 0), 0.10, 0.11, sides=8)
    box(p, "white", "Spine1", (0, 1.21, 0), (0.30, 0.10, 0.19), taper=(1.15, 1.05))
    box(p, "white", "Spine2", (0, 1.36, 0), (0.36, 0.20, 0.22), taper=(1.05, 0.95))
    box(p, "accent", "Spine2", (0, 1.36, 0.111), (0.12, 0.08, 0.01))
    ball(p, "glow", "Spine2", (0, 1.36, 0.115), 0.025)
    # Cou et tête
    prism(p, "dark", "Neck", (0, 1.44, 0), (0, 1.55, 0), 0.045, 0.045)
    box(p, "white", "Head", (0, 1.66, 0), (0.24, 0.22, 0.22), taper=(0.9, 0.9))
    box(p, "visor", "Head", (0, 1.67, 0.106), (0.20, 0.08, 0.02))
    for x in (-0.05, 0.05):
        box(p, "glow", "Head", (x, 1.67, 0.118), (0.04, 0.025, 0.01))
    prism(p, "dark", "Head", (0, 1.77, 0), (0, 1.84, 0), 0.008, 0.008, sides=4)
    ball(p, "accent", "Head", (0, 1.85, 0), 0.02)
    for x in (-1, 1):
        prism(p, "dark", "Head", (0.12 * x, 1.66, 0), (0.15 * x, 1.66, 0), 0.04, 0.035, sides=8)

    for s, x in (("Left", 1), ("Right", -1)):
        # Bras
        ball(p, "accent", f"{s}Arm", w[f"{s}Arm"], 0.075)
        prism(p, "white", f"{s}Arm", w[f"{s}Arm"] + (0.04 * x, 0, 0), w[f"{s}ForeArm"], 0.055, 0.045)
        ball(p, "dark", f"{s}ForeArm", w[f"{s}ForeArm"], 0.058)
        prism(p, "white", f"{s}ForeArm", w[f"{s}ForeArm"], w[f"{s}Hand"], 0.045, 0.05)
        box(p, "dark", f"{s}Hand", w[f"{s}Hand"] + (0.06 * x, 0, 0), (0.11, 0.05, 0.09))
        box(p, "dark", f"{s}Hand", w[f"{s}Hand"] + (0.03 * x, 0, 0.055), (0.04, 0.04, 0.03))
        # Jambes
        ball(p, "dark", f"{s}UpLeg", w[f"{s}UpLeg"], 0.07)
        prism(p, "white", f"{s}UpLeg", w[f"{s}UpLeg"], w[f"{s}Leg"], 0.08, 0.06)
        ball(p, "accent", f"{s}Leg", w[f"{s}Leg"], 0.075)
        prism(p, "white", f"{s}Leg", w[f"{s}Leg"], w[f"{s}Foot"] + (0, 0.04, 0), 0.06, 0.05)
        box(p, "dark", f"{s}Foot", (0.10 * x, 0.045, 0.03), (0.12, 0.09, 0.20), taper=(0.85, 0.8))
        box(p, "accent", f"{s}ToeBase", (0.10 * x, 0.03, 0.165), (0.11, 0.06, 0.07), taper=(0.9, 0.7))
    return p


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "sample/Characters/Robot/Robot.glb"
    print(f"{out} : {export(out, build_body(), 'Robot', 'tools/build_robot.py')} triangles")
