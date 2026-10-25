"""Configurations nommées d'un personnage (exports/<nom>.json) : export de sprite sheet + objets affichés."""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from viewer.sprites.config import ExportConfig, config_from_dict, config_to_dict, load_config

PRESETS_DIR = "exports"
DEFAULT_PRESET = "défaut"
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')


@dataclass
class Preset:
    export: ExportConfig = field(default_factory=ExportConfig)
    objects: list[str] = field(default_factory=list)  # objets attachés, chemins relatifs à Objects/


def _objects(data: dict) -> list[str]:
    """Clé « objects » ; à défaut, noms des anciennes entrées « attachments » (réglage par config)."""
    if "objects" in data:
        return [str(o) for o in data["objects"] if o]
    names = (a.get("object") for a in data.get("attachments", []) if isinstance(a, dict))
    return list(dict.fromkeys(str(n) for n in names if n))


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("objet JSON attendu")
    return data


def _files(character_dir: Path) -> list[Path]:
    d = Path(character_dir) / PRESETS_DIR
    return [p for p in d.glob("*.json") if p.is_file()] if d.is_dir() else []


def preset_path(character_dir: Path, name: str) -> Path:
    return Path(character_dir) / PRESETS_DIR / f"{name}.json"


def list_presets(character_dir: Path) -> list[str]:
    """Noms triés ; sans aucun fichier, la config « défaut » issue des anciens fichiers."""
    names = sorted((p.stem for p in _files(character_dir)), key=str.casefold)
    return names or [DEFAULT_PRESET]


def load_preset(character_dir: Path, name: str) -> tuple[Preset, str | None]:
    """Config du fichier ; le second élément décrit une erreur de lecture."""
    character_dir = Path(character_dir)
    path = preset_path(character_dir, name)
    if not path.is_file():
        if _files(character_dir):
            return Preset(), None
        # Migration : contenu des anciens spritesheet.json et attachments.json.
        export, error = load_config(character_dir / "spritesheet.json")
        legacy = character_dir / "attachments.json"
        try:
            objects = _objects(_read_json(legacy)) if legacy.is_file() else []
        except (ValueError, AttributeError, TypeError) as e:
            objects, error = [], error or f"{legacy.name} illisible : {e}"
        return Preset(export, objects), error
    try:
        data = _read_json(path)
        return Preset(config_from_dict(data), _objects(data)), None
    except (ValueError, AttributeError, TypeError) as e:
        return Preset(), f"{path.name} illisible : {e}"


def save_preset(character_dir: Path, name: str, preset: Preset) -> Path:
    path = preset_path(character_dir, name)
    path.parent.mkdir(exist_ok=True)
    data = config_to_dict(preset.export) | {"objects": list(preset.objects)}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def rename_preset(character_dir: Path, old: str, new: str) -> None:
    """Renomme le fichier ; la config « défaut » migrée (sans fichier) est écrite sous le nouveau nom."""
    source = preset_path(character_dir, old)
    if source.is_file():
        source.rename(preset_path(character_dir, new))
    else:
        save_preset(character_dir, new, load_preset(character_dir, old)[0])


def delete_preset(character_dir: Path, name: str) -> None:
    preset_path(character_dir, name).unlink(missing_ok=True)


def check_name(name: str, existing: list[str], current: str | None = None) -> str | None:
    """Raison du refus d'un nom de config, ou None s'il est valide."""
    if not name:
        return "Nom vide"
    if _INVALID_CHARS.search(name):
        return 'Caractères interdits : < > : " / \\ | ? *'
    if name.endswith("."):
        return "Le nom ne peut pas finir par un point"
    taken = {n.casefold() for n in existing} - ({current.casefold()} if current else set())
    if name.casefold() in taken:
        return f"La config « {name} » existe déjà"
    return None
