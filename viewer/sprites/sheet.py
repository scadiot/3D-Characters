"""Lecture d'une sprite sheet exportée (JSON + PNG) pour la visualiser (sans Qt ni OpenGL)."""
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Frame:
    x: int
    y: int
    width: int
    height: int
    origin_x: int
    origin_y: int


@dataclass
class Sequence:
    orientation: str
    fps: float
    frames: list[Frame]

    def index_at(self, t: float) -> int:
        """Indice de la frame affichée au temps `t` (secondes), en boucle."""
        return int(t * self.fps) % len(self.frames) if self.fps > 0 else 0

    def frame_at(self, t: float) -> Frame:
        return self.frames[self.index_at(t)]


@dataclass
class SheetAnimation:
    name: str
    sequences: list[Sequence] = field(default_factory=list)  # une par orientation, dans l'ordre du fichier

    @property
    def frame_count(self) -> int:
        return max((len(s.frames) for s in self.sequences), default=0)


@dataclass
class Sheet:
    json_path: Path
    image_path: Path
    frame_height: int
    animations: list[SheetAnimation]


def sheet_from_dict(data: dict, json_path: Path) -> Sheet:
    """Lève ValueError / KeyError / TypeError / AttributeError sur une structure invalide."""
    json_path = Path(json_path)
    by_name: dict[str, SheetAnimation] = {}
    for a in data["animations"]:
        frames = [Frame(int(f["x"]), int(f["y"]), int(f["width"]), int(f["height"]),
                        int(f["origin"]["x"]), int(f["origin"]["y"])) for f in a["frames"]]
        if not frames:
            continue
        name = str(a["name"])
        animation = by_name.setdefault(name, SheetAnimation(name))
        animation.sequences.append(Sequence(str(a.get("orientation", "")), float(a.get("fps", 0)), frames))
    return Sheet(json_path, json_path.parent / str(data["image"]), int(data["frameHeight"]),
                 list(by_name.values()))


def load_sheet(json_path: Path) -> Sheet:
    """Lève ValueError (message lisible) si le fichier n'est pas un export de sprite sheet."""
    json_path = Path(json_path)
    try:
        return sheet_from_dict(json.loads(json_path.read_text(encoding="utf-8")), json_path)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"{json_path.name} illisible : {e}") from e


def list_exports(directory: Path) -> list[Path]:
    """Fichiers JSON d'un dossier d'exports, triés par nom."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"), key=lambda p: p.name.lower())
