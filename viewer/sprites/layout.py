"""Calculs de mise en page d'une sprite sheet (sans Qt ni OpenGL)."""
from dataclasses import dataclass

ORIENTATIONS = ("S", "SE", "E", "NE", "N", "NO", "O", "SO")
ANGLES = {name: 45 * i for i, name in enumerate(ORIENTATIONS)}  # S = face caméra, E = regarde à droite
MARGIN = 4  # pixels laissés vides en haut et en bas de chaque frame


def frame_times(duration: float, count: int) -> list[float]:
    """`count` temps répartis uniformément sur la durée ; la fin de la boucle (identique au début)
    est omise, une seule frame donne la pose à t = 0."""
    return [i * duration / count for i in range(count)]


def playback_fps(duration: float, count: int) -> float:
    """Cadence à laquelle jouer `count` frames pour respecter la durée de l'animation."""
    return round(count / duration, 3) if duration > 0 else 0


@dataclass
class Scale:
    pixels_per_unit: float
    ground_y: float  # ligne de sol, en pixels depuis le haut de la frame


def compute_scale(top: float, bottom: float, frame_height: int, margin: int = MARGIN) -> Scale:
    """Échelle commune pour que [bottom, top] (unités monde, bottom ≤ 0) tienne dans la frame,
    à `margin` pixels des bords."""
    bottom = min(bottom, 0.0)
    span = max(top - bottom, 1e-6)
    ppu = max(frame_height - 2 * margin, 1) / span
    return Scale(ppu, margin + top * ppu)


@dataclass
class Placed:
    x: int
    y: int
    width: int
    height: int
    origin_x: int
    origin_y: int


def pack(sequences: list[list[tuple[int, int, int]]], sheet_width: int,
         frame_height: int) -> tuple[list[list[Placed]], int]:
    """Place les frames (largeur, origine x, origine y) à la suite, séquence après séquence,
    retour à la ligne quand la largeur de la feuille est atteinte. Renvoie aussi la hauteur."""
    placed: list[list[Placed]] = []
    row, x = 0, 0
    for sequence in sequences:
        current = []
        for width, origin_x, origin_y in sequence:
            if width > sheet_width:
                raise ValueError(f"frame de {width} px plus large que la feuille ({sheet_width} px)")
            if x + width > sheet_width:
                row += 1
                x = 0
            current.append(Placed(x, row * frame_height, width, frame_height, origin_x, origin_y))
            x += width
        placed.append(current)
    return placed, (row + 1) * frame_height if any(placed) else 0


def build_json(image_name: str, sheet_width: int, sheet_height: int, frame_height: int,
               entries: list[dict]) -> dict:
    """entries : {"name", "orientation", "fps", "frames": [Placed]} par couple animation/orientation."""
    return {
        "image": image_name,
        "width": sheet_width,
        "height": sheet_height,
        "frameHeight": frame_height,
        "animations": [
            {
                "name": e["name"],
                "orientation": e["orientation"],
                "angle": ANGLES[e["orientation"]],
                "fps": e["fps"],
                "frames": [
                    {"x": f.x, "y": f.y, "width": f.width, "height": f.height,
                     "origin": {"x": f.origin_x, "y": f.origin_y}}
                    for f in e["frames"]
                ],
            }
            for e in entries
        ],
    }
