"""Découverte des personnages, skins et animations sous un dossier racine."""
from dataclasses import dataclass, field
import re
from pathlib import Path

from viewer.gltf_loader import LoadError, clip_names

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
_INVALID_FOLDER_CHARS = re.compile(r'[<>:"/\|?*]')


@dataclass
class CharacterEntry:
    name: str
    model_path: Path
    skins: list[Path]                                                   # images de skins/ : tous matériaux
    material_skins: dict[str, list[Path]] = field(default_factory=dict)  # skins/<matériau>/

    def skins_for(self, material: str) -> list[Path]:
        """Skins proposées pour un matériau : son sous-dossier, puis les images communes."""
        key = folder_key(material)
        own = [p for folder, paths in self.material_skins.items() if folder_key(folder) == key for p in paths]
        return own + self.skins

    def unmatched_folders(self, materials: list[str]) -> list[str]:
        keys = {folder_key(m) for m in materials}
        return sorted(f for f in self.material_skins if folder_key(f) not in keys)


def folder_key(name: str) -> str:
    """Nom de matériau tel qu'il peut apparaître comme dossier Windows (casse ignorée)."""
    return _INVALID_FOLDER_CHARS.sub("_", name).casefold()


@dataclass
class AnimationEntry:
    label: str
    path: Path
    clip_index: int
    error: str | None = None


@dataclass
class Library:
    characters: list[CharacterEntry] = field(default_factory=list)
    animations: list[AnimationEntry] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def scan(root: Path) -> Library:
    root = Path(root)
    lib = Library()
    characters_dir, animations_dir = root / "Characters", root / "Animations"
    if not characters_dir.is_dir():
        lib.messages.append(f"Dossier introuvable : {characters_dir}")
    else:
        for d in sorted(p for p in characters_dir.iterdir() if p.is_dir()):
            model = _find_model(d)
            if model is None:
                lib.messages.append(f"Aucun .glb dans {d}")
                continue
            skins_dir = d / "skins"
            material_skins = ({f.name: _find_skins(f) for f in sorted(skins_dir.iterdir()) if f.is_dir()}
                              if skins_dir.is_dir() else {})
            lib.characters.append(CharacterEntry(d.name, model, _find_skins(skins_dir), material_skins))
    if not animations_dir.is_dir():
        lib.messages.append(f"Dossier introuvable : {animations_dir}")
    else:
        for f in sorted(animations_dir.glob("*.glb")):
            lib.animations.extend(_scan_animation(f))
    return lib


def _find_model(d: Path) -> Path | None:
    preferred = d / f"{d.name}.glb"
    if preferred.is_file():
        return preferred
    candidates = sorted(d.glob("*.glb"))
    return candidates[0] if candidates else None


def _find_skins(d: Path) -> list[Path]:
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def _scan_animation(path: Path) -> list[AnimationEntry]:
    try:
        names = clip_names(path)
    except LoadError as e:
        return [AnimationEntry(path.stem, path, 0, str(e))]
    if not names:
        return [AnimationEntry(path.stem, path, 0, "aucune animation dans le fichier")]
    if len(names) == 1:
        return [AnimationEntry(path.stem, path, 0)]
    return [AnimationEntry(f"{path.stem} / {n}", path, i) for i, n in enumerate(names)]
