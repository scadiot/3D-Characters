"""Configuration d'export de sprite sheet, stockée par personnage (spritesheet.json)."""
import json
from dataclasses import dataclass, field
from pathlib import Path

from viewer.sprites.layout import ORIENTATIONS

SHEET_WIDTH_RANGE = (64, 16384)
FRAME_HEIGHT_RANGE = (16, 2048)
FPS_RANGE = (1, 60)


@dataclass
class AnimationExport:
    name: str
    fps: int = 12
    orientations: list[str] = field(default_factory=lambda: ["S"])


@dataclass
class ExportConfig:
    sheet_width: int = 1000
    frame_height: int = 250
    animations: list[AnimationExport] = field(default_factory=list)


def _clamp(value, bounds: tuple[int, int], default: int) -> int:
    try:
        return min(max(int(value), bounds[0]), bounds[1])
    except (TypeError, ValueError):
        return default


def load_config(path: Path) -> tuple[ExportConfig, str | None]:
    """Config du fichier, ou config par défaut ; le second élément décrit une erreur de lecture."""
    path = Path(path)
    if not path.is_file():
        return ExportConfig(), None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        animations = []
        for a in data.get("animations", []):
            if not isinstance(a, dict) or not a.get("name"):
                continue
            wanted = set(a.get("orientations", []))
            animations.append(AnimationExport(
                str(a["name"]),
                _clamp(a.get("fps", 12), FPS_RANGE, 12),
                [o for o in ORIENTATIONS if o in wanted],
            ))
        return ExportConfig(
            _clamp(data.get("sheetWidth", 1000), SHEET_WIDTH_RANGE, 1000),
            _clamp(data.get("frameHeight", 250), FRAME_HEIGHT_RANGE, 250),
            animations,
        ), None
    except (ValueError, AttributeError) as e:
        return ExportConfig(), f"{path.name} illisible : {e}"


def save_config(path: Path, config: ExportConfig) -> None:
    data = {
        "sheetWidth": config.sheet_width,
        "frameHeight": config.frame_height,
        "animations": [{"name": a.name, "fps": a.fps, "orientations": a.orientations} for a in config.animations],
    }
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
