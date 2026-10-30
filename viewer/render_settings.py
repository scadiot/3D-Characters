"""Paramètres de rendu (standard ou cel shading), communs à la vue et à l'export de sprites."""
import math
from dataclasses import asdict, dataclass

import numpy as np

SHADINGS = ("standard", "cel")
BANDS_RANGE = (2, 8)
OUTLINE_WIDTH_RANGE = (0.0, 10.0)  # pixels de l'image finale
ELEVATION_RANGE = (-90, 90)


@dataclass
class RenderSettings:
    shading: str = "cel"
    bands: int = 3  # nombre de tons du dégradé lumière -> ombre
    softness: float = 0.05  # largeur de la transition entre deux tons (0 : net)
    shadow: float = 0.35  # luminosité des zones non éclairées
    rim: float = 0.25  # intensité du liseré de lumière sur les bords
    rim_width: float = 0.3
    outline: bool = True
    outline_width: float = 1.5
    outline_color: tuple[float, float, float] = (0.08, 0.06, 0.06)
    light_azimuth: int = 34  # degrés, 0 : lumière venant de +Z (face au personnage)
    light_elevation: int = 54

    def light_dir(self) -> tuple[float, float, float]:
        """Direction de propagation de la lumière (vers la scène), normée."""
        az, el = math.radians(self.light_azimuth), math.radians(self.light_elevation)
        return (-math.cos(el) * math.sin(az), -math.sin(el), -math.cos(el) * math.cos(az))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["outline_color"] = list(self.outline_color)
        return data

    @classmethod
    def from_dict(cls, data) -> "RenderSettings":
        """Valeurs absentes ou invalides remplacées par les défauts, les autres ramenées dans leurs bornes."""
        d = cls()
        if not isinstance(data, dict):
            return d

        def num(key, lo, hi, cast=float):
            try:
                value = cast(data[key])
            except (KeyError, TypeError, ValueError, OverflowError):
                return getattr(d, key)
            return getattr(d, key) if math.isnan(value) else min(max(value, lo), hi)

        color = data.get("outline_color")
        try:
            color = tuple(min(max(float(c), 0.0), 1.0) for c in color)
        except (TypeError, ValueError):
            color = d.outline_color
        return cls(
            shading=data.get("shading") if data.get("shading") in SHADINGS else d.shading,
            bands=num("bands", *BANDS_RANGE, cast=int),
            softness=num("softness", 0.0, 0.5),
            shadow=num("shadow", 0.0, 1.0),
            rim=num("rim", 0.0, 1.0),
            rim_width=num("rim_width", 0.0, 1.0),
            outline=bool(data.get("outline", d.outline)),
            outline_width=num("outline_width", *OUTLINE_WIDTH_RANGE),
            outline_color=color if len(color) == 3 else d.outline_color,
            light_azimuth=num("light_azimuth", -180, 180, cast=int),
            light_elevation=num("light_elevation", *ELEVATION_RANGE, cast=int),
        )


def camera_eye(view_proj: np.ndarray) -> np.ndarray:
    """Position de la caméra (w = 1), ou direction vers la caméra (w = 0) pour une projection orthographique."""
    eye = np.linalg.inv(view_proj) @ np.array([0.0, 0.0, -1.0, 0.0])
    if abs(eye[3]) > 1e-6 * np.linalg.norm(eye[:3]):
        return eye / eye[3]
    return np.append(eye[:3] / np.linalg.norm(eye[:3]), 0.0)


def smooth_normals(positions: np.ndarray, normals: np.ndarray) -> np.ndarray:
    """Normales moyennées entre sommets confondus : le contour extrudé reste fermé aux arêtes vives."""
    if not len(positions):
        return normals
    keys = np.round(np.asarray(positions, dtype=np.float64) / 1e-5).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    sums = np.zeros((inverse.max() + 1, 3))
    np.add.at(sums, inverse, normals)
    out = sums[inverse]
    length = np.linalg.norm(out, axis=1, keepdims=True)
    return np.where(length > 1e-8, out / np.maximum(length, 1e-12), normals)
