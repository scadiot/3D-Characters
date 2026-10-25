"""Configurations nommées d'un personnage (exports/<nom>.json) : export de sprite sheet + objets attachés."""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from viewer.attachments import Attachment, attachments_from_data, attachments_to_data, load_attachments
from viewer.sprites.config import ExportConfig, config_from_dict, config_to_dict, load_config

PRESETS_DIR = "exports"
DEFAULT_PRESET = "défaut"
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')


@dataclass
class Preset:
    export: ExportConfig = field(default_factory=ExportConfig)
    attachments: list[Attachment] = field(default_factory=list)


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
        export, export_error = load_config(character_dir / "spritesheet.json")
        attachments, attachments_error = load_attachments(character_dir / "attachments.json")
        return Preset(export, attachments), export_error or attachments_error
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Preset(config_from_dict(data), attachments_from_data(data.get("attachments", []))), None
    except (ValueError, AttributeError, TypeError) as e:
        return Preset(), f"{path.name} illisible : {e}"


def save_preset(character_dir: Path, name: str, preset: Preset) -> Path:
    path = preset_path(character_dir, name)
    path.parent.mkdir(exist_ok=True)
    data = config_to_dict(preset.export) | {"attachments": attachments_to_data(preset.attachments)}
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
