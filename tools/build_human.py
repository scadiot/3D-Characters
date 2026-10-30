"""Génère un humain low poly sur squelette Mixamo : sample/Characters/Human/Human.glb.

Torse, membres et tête sont des lofts d'anneaux ; les anneaux placés aux articulations
sont partagés entre deux bones pour que la peau reste continue quand le membre plie.

    python tools/build_human.py [chemin_sortie.glb]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from lowpoly import Part, Rig, ball, box, export, grid_uvs, loft, prism

ATLAS_SIZE = 2048

# (nom, parent, position monde en T-pose)
_CENTER = [
    ("Hips", None, (0, 0.98, 0)),
    ("Spine", "Hips", (0, 1.07, 0)),
    ("Spine1", "Spine", (0, 1.18, 0)),
    ("Spine2", "Spine1", (0, 1.30, 0)),
    ("Neck", "Spine2", (0, 1.48, 0)),
    ("Head", "Neck", (0, 1.57, 0)),
    ("HeadTop_End", "Head", (0, 1.77, 0)),
]


def _side(s: str, x: float) -> list:
    return [
        (f"{s}Shoulder", "Spine2", (0.05 * x, 1.44, 0)),
        (f"{s}Arm", f"{s}Shoulder", (0.18 * x, 1.43, 0)),
        (f"{s}ForeArm", f"{s}Arm", (0.44 * x, 1.43, 0)),
        (f"{s}Hand", f"{s}ForeArm", (0.68 * x, 1.43, 0)),
        (f"{s}UpLeg", "Hips", (0.09 * x, 0.93, 0)),
        (f"{s}Leg", f"{s}UpLeg", (0.09 * x, 0.52, 0)),
        (f"{s}Foot", f"{s}Leg", (0.09 * x, 0.09, -0.01)),
        (f"{s}ToeBase", f"{s}Foot", (0.09 * x, 0.02, 0.11)),
        (f"{s}Toe_End", f"{s}ToeBase", (0.09 * x, 0.02, 0.19)),
    ]


RIG = Rig(_CENTER + _side("Left", 1) + _side("Right", -1))

COLORS = {
    "skin": (0.88, 0.68, 0.54, 1),
    "hair": (0.24, 0.15, 0.09, 1),
    "shirt": (0.20, 0.46, 0.74, 1),
    "jeans": (0.17, 0.22, 0.36, 1),
    "belt": (0.32, 0.20, 0.12, 1),
    "shoe": (0.14, 0.14, 0.15, 1),
    "sole": (0.90, 0.90, 0.88, 1),
    "eye": (0.08, 0.07, 0.07, 1),
    "mouth": (0.62, 0.36, 0.32, 1),
    "iris": (0.33, 0.20, 0.11, 1),
}

# skins : couleurs changées par variante ; chacune donne skins/body/<nom>.png (atlas du corps)
# et skins/face/<nom>.png (visage), proposées séparément par la visionneuse
SKINS = {
    "blond_rouge": {"hair": (0.85, 0.68, 0.36, 1), "shirt": (0.78, 0.16, 0.16, 1), "jeans": (0.36, 0.48, 0.66, 1),
                    "iris": (0.25, 0.45, 0.72, 1)},
    "brun_vert": {"skin": (0.48, 0.31, 0.21, 1), "hair": (0.06, 0.05, 0.05, 1), "shirt": (0.22, 0.55, 0.32, 1),
                  "jeans": (0.66, 0.58, 0.42, 1), "mouth": (0.36, 0.20, 0.18, 1), "iris": (0.16, 0.09, 0.05, 1)},
    "roux_moutarde": {"skin": (0.96, 0.80, 0.70, 1), "hair": (0.72, 0.30, 0.10, 1),
                      "shirt": (0.86, 0.66, 0.16, 1), "jeans": (0.28, 0.28, 0.30, 1), "iris": (0.30, 0.52, 0.30, 1)},
    "costume": {"shirt": (0.26, 0.27, 0.30, 1), "jeans": (0.20, 0.21, 0.24, 1), "belt": (0.06, 0.06, 0.06, 1),
                "shoe": (0.10, 0.07, 0.05, 1), "sole": (0.08, 0.06, 0.05, 1)},
    "sport": {"hair": (0.12, 0.09, 0.07, 1), "shirt": (0.93, 0.93, 0.93, 1), "jeans": (0.10, 0.10, 0.11, 1),
              "belt": (0.10, 0.10, 0.11, 1), "shoe": (0.85, 0.20, 0.15, 1)},
}


def _mix(a: str, b: str, wa: float = 0.5) -> dict:
    return {a: wa, b: 1 - wa}


def _shoulders(point) -> dict:
    """Haut du buste : le bord des épaules suit en partie la clavicule et le bras, le centre reste au buste."""
    s = "Left" if point[0] > 0 else "Right"
    t = float(np.clip((abs(point[0]) - 0.10) / 0.08, 0, 1))
    return {"Spine2": 1 - 0.45 * t, f"{s}Shoulder": 0.25 * t, f"{s}Arm": 0.20 * t}


def _hips(leg_share: float):
    """Bas du bassin : hors de l'axe, les sommets suivent la cuisse de leur côté jusqu'à `leg_share`."""
    def influence(point) -> dict:
        t = float(np.clip((abs(point[0]) - 0.03) / 0.09, 0, 1)) * leg_share
        return {"Hips": 1 - t, ("LeftUpLeg" if point[0] > 0 else "RightUpLeg"): t}
    return influence


def _torso(p: Part) -> None:
    # anneaux (y, demi-largeur, demi-profondeur, décalage z, influence)
    rings = [
        (0.855, 0.120, 0.082, 0.00, _hips(0.6)),     # entrejambe
        (0.895, 0.188, 0.100, -0.005, _hips(0.45)),  # haut des cuisses, au ras de leur bord extérieur
        (0.945, 0.190, 0.104, -0.006, _hips(0.2)),   # hanches
        (1.00, 0.168, 0.096, 0.00, "Hips"),
        (1.03, 0.155, 0.093, 0.00, _mix("Hips", "Spine")),
        (1.12, 0.145, 0.090, 0.005, "Spine"),
        (1.22, 0.155, 0.098, 0.01, _mix("Spine1", "Spine2", 0.6)),
        (1.33, 0.175, 0.105, 0.015, "Spine2"),
        (1.40, 0.200, 0.100, 0.008, _shoulders),
        (1.465, 0.180, 0.085, 0.00, _shoulders),   # dessus des épaules, au niveau du haut des manches
        (1.495, 0.105, 0.068, 0.00, _mix("Spine2", "Neck", 0.8)),
    ]
    colors = ["jeans", "jeans", "jeans", "belt"] + ["shirt"] * (len(rings) - 5)
    loft(p, colors, (0, 1, 0), [((0, y, z), (rx, rz), i) for y, rx, rz, z, i in rings], sides=10, seam=(0, 0, -1))
    box(p, "belt", "Hips", (0, 1.015, 0.093), (0.05, 0.035, 0.01))


# profil du crâne : (y, décalage z, demi-largeur, demi-profondeur)
_HEAD = [
    (1.530, 0.035, 0.045, 0.040),   # menton
    (1.545, 0.030, 0.060, 0.060),
    (1.570, 0.020, 0.075, 0.080),   # mâchoire
    (1.600, 0.014, 0.083, 0.090),
    (1.640, 0.010, 0.088, 0.098),   # pommettes
    (1.675, 0.007, 0.0905, 0.100),
    (1.710, 0.005, 0.090, 0.100),   # front
    (1.740, 0.002, 0.083, 0.093),
    (1.760, 0.000, 0.070, 0.080),
    (1.775, 0.000, 0.052, 0.060),
    (1.785, 0.000, 0.030, 0.035),
]

# limite basse des cheveux selon l'angle depuis l'avant (degrés, côté gauche ; le droit est symétrique) :
# frange en pointes, tempes, pattes devant l'oreille, dégagé au-dessus, nuque
_HAIRLINE = [(0, 1.698), (15, 1.716), (30, 1.700), (45, 1.712), (60, 1.692), (75, 1.650),
             (90, 1.676), (105, 1.668), (120, 1.628), (135, 1.598), (150, 1.582), (180, 1.578)]


def _skull(y: float) -> tuple[float, float, float]:
    """(décalage z, demi-largeur, demi-profondeur) du crâne à la hauteur y."""
    ys = [r[0] for r in _HEAD]
    return tuple(float(np.interp(y, ys, [r[k] for r in _HEAD])) for k in (1, 2, 3))


_FACE_TOP = 1.710          # anneau du front : au-dessus, la peau est cachée par les cheveux
_FACE_HALF_DEG = 78.75     # le visage couvre ±78,75° (7 colonnes de chaque côté), jusqu'aux oreilles
_HEAD_COLUMNS = 32
FACE_SIZE = 512
FACE_COLORS = {"skin", "hair", "mouth", "eye", "iris"}  # couleurs utilisées par face_image


def _skull_point(theta: float, y: float) -> np.ndarray:
    """Point du crâne à l'angle theta (0 = devant, positif vers la gauche +X) et à la hauteur y."""
    z, rx, rz = _skull(y)
    return np.array([rx * np.sin(theta), y, z + rz * np.cos(theta)])


def _ring_arc(theta: float, y: float, steps: int = 64) -> float:
    """Longueur d'arc signée le long de l'anneau horizontal, depuis le milieu du visage."""
    _, rx, rz = _skull(y)
    t = np.linspace(0, theta, steps)
    return float(np.trapezoid(np.hypot(rx * np.cos(t), rz * np.sin(t)), t))


def _column_arc(theta: float, y: float, steps: int = 64) -> float:
    """Longueur d'arc le long du profil vertical, du haut du visage jusqu'à y."""
    pts = np.array([_skull_point(theta, yy) for yy in np.linspace(_FACE_TOP, y, steps)])
    return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())


class _FaceUV:
    """Dépliage du visage à longueurs d'arc réelles : même échelle en u et en v, sans étirement notable.
    v = 0 en haut de l'image (convention glTF)."""

    margin = 0.04

    def __init__(self):
        thetas = np.radians(np.linspace(-_FACE_HALF_DEG, _FACE_HALF_DEG, 15))
        ys = [y for y, *_ in _HEAD if y <= _FACE_TOP]
        width = 2 * max(abs(_ring_arc(t, y)) for t in thetas for y in ys)
        height = max(_column_arc(t, ys[0]) for t in thetas)
        self.length = max(width, height) / (1 - 2 * self.margin)  # mètres couverts par la texture
        self.v0 = 0.5 - height / (2 * self.length)

    def __call__(self, theta: float, y: float) -> tuple[float, float]:
        return 0.5 + _ring_arc(theta, y) / self.length, self.v0 + _column_arc(theta, y) / self.length

    def at(self, x: float, y: float) -> tuple[float, float]:
        """UV du point de la face avant à l'abscisse x."""
        return self(float(np.arcsin(np.clip(x / _skull(y)[1], -1, 1))), y)


def _rgb(color, factor: float = 1.0, alpha: int = 255) -> tuple:
    return (*(int(np.clip(c * factor, 0, 1) * 255) for c in color[:3]), alpha)


def _blend(a, b, t: float) -> tuple:
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def face_image(colors: dict, size: int = FACE_SIZE, eyes: float = 1.0) -> Image.Image:
    """Texture du visage : peau, joues, sourcils, yeux, nez et bouche peints aux positions du dépliage.
    eyes : facteur de taille des yeux (plus grands pour un enfant)."""
    uv = _FaceUV()
    ss = 2 * size  # sur-échantillonnage, réduit à la fin pour l'anticrénelage
    skin, hair, mouth, eye, iris = (colors[k] for k in ("skin", "hair", "mouth", "eye", "iris"))
    img = Image.new("RGBA", (ss, ss), _rgb(skin))

    def P(x, y):
        u, v = uv.at(x, y)
        return u * ss, v * ss

    def m(meters):
        return meters / uv.length * ss

    def oval(draw, x, y, rx, ry, fill):
        cx, cy = P(x, y)
        draw.ellipse((cx - m(rx), cy - m(ry), cx + m(rx), cy + m(ry)), fill=fill)

    def soft(paint, blur):
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        paint(ImageDraw.Draw(layer))
        img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(m(blur))))

    def cheeks(d):
        for sx in (-1, 1):
            oval(d, sx * 0.052, 1.612, 0.016, 0.010, _rgb(_blend(skin, (0.95, 0.50, 0.50), 0.30), alpha=70))

    def shadows(d):
        oval(d, 0, 1.6205, 0.011, 0.0035, _rgb(skin, 0.80, 70))  # dessous du nez, le relief fait le reste
        oval(d, 0, 1.584, 0.011, 0.0025, _rgb(skin, 0.85, 120))  # sous la lèvre

    soft(cheeks, 0.006)
    soft(shadows, 0.002)
    soft(lambda d: oval(d, 0.002, 1.631, 0.006, 0.004, _rgb(skin, 1.08, 90)), 0.002)  # reflet du nez

    d = ImageDraw.Draw(img)
    for sx in (-1, 1):  # narines
        oval(d, sx * 0.0065, 1.6235, 0.0028, 0.0016, _rgb(skin, 0.5))

    # bouche : lèvre inférieure, lèvre supérieure en arc de Cupidon, commissure
    oval(d, 0, 1.5895, 0.016, 0.0045, _rgb(mouth))
    d.polygon([P(-0.021, 1.594), P(-0.008, 1.598), P(0, 1.5965), P(0.008, 1.598), P(0.021, 1.594),
               P(0, 1.5925)], fill=_rgb(mouth, 0.88))
    d.line([P(-0.021, 1.594), P(0, 1.5925), P(0.021, 1.594)], fill=_rgb(mouth, 0.45), width=round(m(0.0014)))

    for sx in (-1, 1):
        cx, cy = sx * 0.034, 1.655
        # blanc de l'œil, puis iris et pupille découpés dans sa forme
        mask = Image.new("L", img.size, 0)
        ex, ey = 0.0135 * eyes, 0.0075 * eyes
        oval(ImageDraw.Draw(mask), cx, cy, ex, ey, 255)
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        oval(ld, cx, cy, ex, ey, (245, 242, 235, 255))
        oval(ld, cx, cy + 0.0005, 0.0068 * eyes, 0.0068 * eyes, _rgb(iris))
        oval(ld, cx, cy + 0.0005, 0.0032 * eyes, 0.0032 * eyes, _rgb(eye))
        oval(ld, cx + 0.0025 * eyes, cy + 0.0028 * eyes, 0.0016 * eyes, 0.0016 * eyes, (255, 255, 255, 255))
        img.paste(layer, (0, 0), mask)
        # paupière supérieure et cil extérieur, paupière inférieure discrète
        (x0, y0), (x1, y1) = P(cx - ex, cy + ey), P(cx + ex, cy - ey)
        lid = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        d.arc(lid, 180, 360, fill=_rgb(eye), width=round(m(0.0022)))
        d.arc(lid, 20, 160, fill=_rgb(skin, 0.78), width=round(m(0.0009)))
        d.line([P(cx + sx * (ex - 0.0005), cy + 0.0010), P(cx + sx * (ex + 0.0040), cy + 0.0040)], fill=_rgb(eye),
               width=round(m(0.0018)))
        # sourcil : plus épais côté nez, légèrement arqué
        t = np.linspace(-1, 1, 9)
        brow = list(zip(sx * (0.034 + 0.018 * t), 1.680 + 0.0035 * (1 - t ** 2), 0.0055 - 0.00125 * (t + 1)))
        d.polygon([P(x, y + h / 2) for x, y, h in brow] + [P(x, y - h / 2) for x, y, h in reversed(brow)],
                  fill=_rgb(hair, 0.8))
    return img.resize((size, size), Image.LANCZOS)


def _hair(p: Part, columns=32, rows=9) -> None:
    """Coque qui épouse le crâne au-dessus de la ligne d'implantation, plus épaisse sur le dessus."""
    top = 1.78
    deg, line = zip(*_HAIRLINE)
    grid = []
    for i in range(columns):
        theta = 2 * np.pi * i / columns
        bottom = float(np.interp(np.degrees(min(theta, 2 * np.pi - theta)), deg, line))
        direction = np.array([np.sin(theta), 0, np.cos(theta)])
        column = []
        for k in range(-1, rows + 1):
            y = bottom + (top - bottom) * max(k, 0) / rows
            z, rx, rz = _skull(y)
            # rangée -1 : rebord rentrant vers la peau, pour que la coque ne paraisse pas en papier
            thickness = -0.003 if k < 0 else 0.010 + 0.016 * np.clip((y - 1.62) / 0.15, 0, 1)
            column.append(np.array([0, y, z]) + direction * (rx + thickness, 0, rz + thickness))
        grid.append(column)
    crown = np.array([0, 1.806, -0.004])
    # dépliage : le tour en bande coupée derrière la tête, le dessus (presque horizontal) vu de dessus
    order = [(columns // 2 + i) % columns for i in range(columns)]
    uv, band, cap = grid_uvs([[grid[c][k] for c in order] for k in range(rows + 2)]), p.chart(), p.chart()
    flat = lambda *pts: [(q[0], -q[2]) for q in pts]
    for i in range(columns):
        a, b = grid[order[i]], grid[order[(i + 1) % columns]]
        for k in range(rows + 1):
            quad = (a[k], b[k], b[k + 1], a[k + 1])
            if k < rows - 1:
                p.quad("hair", "Head", *quad, uvs=(uv[k][i], uv[k][i + 1], uv[k + 1][i + 1], uv[k + 1][i]),
                       chart=band)
            else:
                p.quad("hair", "Head", *quad, uvs=flat(*quad), chart=cap)
        p.tri("hair", "Head", a[-1], b[-1], crown, uvs=flat(a[-1], b[-1], crown), chart=cap)


# relief du nez : cellules de la grille subdivisées (±2 colonnes, anneaux 1,60 → 1,675)
_NOSE_HALF = np.radians(22.5) + 1e-9
_NOSE_Y = (1.600, 1.675)
_NOSE_SUBDIV = (3, 6)  # (colonnes, rangées) par cellule


def _nose_height(x: float, y: float) -> float:
    """Saillie vers l'avant : arête qui monte de l'entre-deux-yeux à la pointe, puis retombe sous les narines."""
    bridge_top, tip, base = 1.668, 1.630, 1.617
    if y >= bridge_top or y <= base:
        return 0.0
    if y >= tip:
        t = (bridge_top - y) / (bridge_top - tip)
        h, half_width = 0.013 * t ** 1.3, 0.0055 + 0.0065 * t
    else:
        t = (y - base) / (tip - base)
        h, half_width = 0.013 * t ** 0.6, 0.012
    return h * max(0.0, 1 - (x / half_width) ** 2) ** 0.7


def _relief_cell(p: Part, corners, uvs) -> None:
    """Cellule du visage subdivisée par interpolation bilinéaire de ses coins, puis déplacée par le nez.
    Les bords restent sur les arêtes d'origine : pas de fissure avec les cellules voisines."""
    (A, B, C, D), (uA, uB, uC, uD) = (np.asarray(c, float) for c in corners), (np.asarray(u) for u in uvs)
    nu, nv = _NOSE_SUBDIV

    def at(i, j):
        s, t = i / nu, j / nv
        point = (1 - s) * (1 - t) * A + s * (1 - t) * B + s * t * C + (1 - s) * t * D
        point[2] += _nose_height(point[0], point[1])
        return point, tuple((1 - s) * (1 - t) * uA + s * (1 - t) * uB + s * t * uC + (1 - s) * t * uD)

    pts = [[at(i, j) for j in range(nv + 1)] for i in range(nu + 1)]
    for i in range(nu):
        for j in range(nv):
            (a, ua), (b, ub), (c, uc), (d, ud) = pts[i][j], pts[i + 1][j], pts[i + 1][j + 1], pts[i][j + 1]
            p.tri("face", "Head", a, b, c, uvs=(ua, ub, uc))
            p.tri("face", "Head", a, c, d, uvs=(ua, uc, ud))


def _head(p: Part) -> None:
    loft(p, "skin", (0, 1, 0), [
        ((0, 1.45, 0.0), (0.045, 0.045), _mix("Spine2", "Neck")),
        ((0, 1.53, 0.005), (0.045, 0.045), _mix("Neck", "Head")),
    ], caps=(False, False), seam=(0, 0, -1))
    # crâne : grille colonnes × anneaux de _HEAD ; l'avant forme le mesh « face », déplié par _FaceUV ;
    # le reste (peau de l'atlas) est déplié en bande coupée au milieu du front, sous les cheveux
    uv = _FaceUV()
    thetas = [2 * np.pi * i / _HEAD_COLUMNS for i in range(_HEAD_COLUMNS + 1)]
    signed = [t - 2 * np.pi if t > np.pi + 1e-9 else t for t in thetas]
    signed[-1] = 0.0
    grid = [[_skull_point(t, y) for y, *_ in _HEAD] for t in thetas]
    skin_uv = grid_uvs([[grid[i][k] for i in range(_HEAD_COLUMNS)] for k in range(len(_HEAD))])
    skin_chart, chin_chart, crown_chart = p.chart(), p.chart(), p.chart()
    limit = np.radians(_FACE_HALF_DEG) + 1e-9
    chin, crown = np.array([0, _HEAD[0][0], _HEAD[0][1]]), np.array([0, _HEAD[-1][0], _HEAD[-1][1]])
    flat = lambda *pts: [(q[0], q[2]) for q in pts]  # bouchons projetés sur le plan horizontal
    for i in range(_HEAD_COLUMNS):
        a, b, ta, tb = grid[i], grid[i + 1], signed[i], signed[i + 1]
        in_face = abs(ta) <= limit and abs(tb) <= limit
        for k in range(len(_HEAD) - 1):
            ya, yb = _HEAD[k][0], _HEAD[k + 1][0]
            corners = (a[k], b[k], b[k + 1], a[k + 1])
            uvs = (uv(ta, ya), uv(tb, ya), uv(tb, yb), uv(ta, yb))
            if in_face and abs(ta) <= _NOSE_HALF and abs(tb) <= _NOSE_HALF and ya >= _NOSE_Y[0] and yb <= _NOSE_Y[1]:
                _relief_cell(p, corners, uvs)
            elif in_face and yb <= _FACE_TOP:
                p.tri("face", "Head", *corners[:3], uvs=uvs[:3])
                p.tri("face", "Head", corners[0], corners[2], corners[3], uvs=(uvs[0], uvs[2], uvs[3]))
            else:
                p.quad("skin", "Head", *corners, chart=skin_chart,
                       uvs=(skin_uv[k][i], skin_uv[k][i + 1], skin_uv[k + 1][i + 1], skin_uv[k + 1][i]))
        p.tri("skin", "Head", b[0], a[0], chin, uvs=flat(b[0], a[0], chin), chart=chin_chart)
        p.tri("skin", "Head", a[-1], b[-1], crown, uvs=flat(a[-1], b[-1], crown), chart=crown_chart)
    _hair(p)
    for x in (-1, 1):
        ear = (_skull(1.645)[1] * x, 1.645, 0.0)
        ball(p, "skin", "Head", ear, 0.025, scale=(0.5, 1.0, 0.8), detail=1)  # oreilles


def _arm(p: Part, s: str, x: float) -> None:
    w = RIG.world
    shoulder, arm, fore, hand = (f"{s}{b}" for b in ("Shoulder", "Arm", "ForeArm", "Hand"))
    y = w[arm][1]
    rings = [
        (0.11, (0.060, 0.065), _mix(shoulder, arm, 0.6)),
        (0.19, (0.058, 0.058), arm),
        (0.30, (0.052, 0.052), arm),   # fin de manche
        (0.30, (0.048, 0.048), arm),
        (0.44, (0.041, 0.043), _mix(arm, fore)),
        (0.56, (0.042, 0.046), fore),
        (0.67, (0.028, 0.034), _mix(fore, hand)),
    ]
    colors = ["shirt", "shirt", "shirt", "skin", "skin", "skin"]
    loft(p, colors, (x, 0, 0), [((d * x, y, 0), r, i) for d, r, i in rings], sides=8, seam=(0, -1, 0))
    # main en moufle, pouce à l'avant
    loft(p, "skin", (x, 0, 0), [
        ((0.67 * x, y, 0), (0.028, 0.034), _mix(fore, hand)),
        ((0.73 * x, y - 0.003, 0.003), (0.021, 0.050), hand),
        ((0.81 * x, y - 0.006, 0.003), (0.016, 0.045), hand),
        ((0.85 * x, y - 0.008, 0.002), (0.008, 0.025), hand),
    ], sides=6, seam=(0, -1, 0))
    prism(p, "skin", hand, (0.70 * x, y - 0.006, 0.030), (0.76 * x, y - 0.012, 0.062), 0.012, 0.009, sides=5)


def _leg(p: Part, s: str, x: float) -> None:
    upleg, leg, foot, toe = (f"{s}{b}" for b in ("UpLeg", "Leg", "Foot", "ToeBase"))
    cx = 0.09 * x
    rings = [
        (0.97, (0.088, 0.092), _mix("Hips", upleg)),
        (0.88, (0.086, 0.090), upleg),
        (0.70, (0.070, 0.072), upleg),
        (0.52, (0.055, 0.058), _mix(upleg, leg)),
        (0.38, (0.056, 0.060), leg),
        (0.16, (0.045, 0.048), leg),
        (0.11, (0.047, 0.050), _mix(leg, foot)),  # ourlet du jean
    ]
    loft(p, "jeans", (0, -1, 0), [((cx, y, 0.0), r, i) for y, r, i in rings], sides=8, seam=(-x, 0, 0))
    # chaussure : talon lié au pied, avant lié aux orteils
    ankle = _mix(leg, foot, 0.3)
    loft(p, "shoe", (0, 0, 1), [
        ((cx, 0.06, -0.075), (0.040, 0.045), foot),
        ((cx, 0.065, -0.02), (0.048, 0.052), foot),
        ((cx, 0.055, 0.08), (0.040, 0.055), _mix(foot, toe)),
        ((cx, 0.045, 0.16), (0.030, 0.050), toe),
        ((cx, 0.040, 0.20), (0.020, 0.035), toe),
    ], sides=8, seam=(0, -1, 0))
    prism(p, "shoe", ankle, (cx, 0.06, -0.015), (cx, 0.13, -0.01), 0.048, 0.045, sides=8, seam=(0, 0, -1))
    box(p, "sole", foot, (cx, 0.012, 0.01), (0.10, 0.024, 0.19))
    box(p, "sole", toe, (cx, 0.012, 0.155), (0.09, 0.024, 0.10), taper=(1.0, 1.0))


def face_layout(p: Part, face: Image.Image) -> Image.Image:
    """Gabarit du visage : texture par défaut et arêtes des triangles du mesh « face »."""
    image = face.convert("RGB")
    draw = ImageDraw.Draw(image)
    for e in p.groups["face"]:
        draw.polygon([tuple(q * image.size[0]) for q in e[2]], outline=(20, 20, 20))
    return image


def build_body(colors: dict = COLORS, warp=None) -> Part:
    """warp : déformation des proportions (positions et squelette), voir build_child.py."""
    p = Part(RIG.warped(warp) if warp else RIG, colors, textured=("face",), warp=warp)
    _torso(p)
    _head(p)
    for s, x in (("Left", 1), ("Right", -1)):
        _arm(p, s, x)
        _leg(p, s, x)
    return p


def generate(out: Path, name: str, colors: dict = COLORS, skins: dict = SKINS, warp=None, eyes: float = 1.0) -> None:
    """Écrit le GLB, ses skins (skins/body, skins/face) et les gabarits d'UV (uv/)."""
    body = build_body(colors, warp)
    texels = body.pack(ATLAS_SIZE)
    face = lambda c: face_image(c, eyes=eyes)
    triangles = export(out, body, name, "tools/build_human.py", atlas=body.paint(), textures={"face": face(colors)})
    print(f"{out} : {triangles} triangles, atlas {ATLAS_SIZE} px à {texels:.0f} px/m")
    # gabarits pour peindre les textures à la main (hors de skins/, qui ne contient que des skins)
    (out.parent / "uv").mkdir(exist_ok=True)
    body.layout().save(out.parent / "uv" / "body.png")
    face_layout(body, face(colors)).save(out.parent / "uv" / "face.png")
    for material, render in (("body", body.paint), ("face", face)):
        folder = out.parent / "skins" / material
        folder.mkdir(parents=True, exist_ok=True)
        for skin, overrides in skins.items():
            if material == "face" and not overrides.keys() & FACE_COLORS:
                continue  # visage identique à celui par défaut
            render({**colors, **overrides}).save(folder / f"{skin}.png")
    print(f"skins écrits dans {out.parent / 'skins'}")


if __name__ == "__main__":
    generate(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "sample/Characters/Human/Human.glb",
             "Human")
