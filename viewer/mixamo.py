"""Convention de nommage des bones Mixamo."""
import re
from dataclasses import dataclass
from typing import Iterable

_PREFIX = re.compile(r"^mixamorig\d*[:_]")


def normalize(name: str) -> str:
    return _PREFIX.sub("", name)


_SIDES = ("Left", "Right")
MIXAMO_CORE = frozenset([
    "Hips", "Spine", "Spine1", "Spine2", "Neck", "Head",
    *(f"{s}{b}" for s in _SIDES
      for b in ("Shoulder", "Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot", "ToeBase")),
])
MIXAMO_OPTIONAL = frozenset([
    "HeadTop_End", "LeftEye", "RightEye",
    *(f"{s}Toe_End" for s in _SIDES),
    *(f"{s}Hand{finger}{k}" for s in _SIDES
      for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky") for k in range(1, 5)),
])
MIXAMO_ALL = MIXAMO_CORE | MIXAMO_OPTIONAL


@dataclass
class ValidationReport:
    missing_core: list[str]       # avertissement
    unmatched_tracks: list[str]   # avertissement
    unknown_bones: list[str]      # info
    missing_optional: list[str]   # info
    unanimated: list[str]         # info

    @property
    def warnings(self) -> int:
        return len(self.missing_core) + len(self.unmatched_tracks)

    @property
    def ok(self) -> bool:
        return self.warnings == 0

    def details(self) -> str:
        sections = [
            ("Bones Mixamo manquants", self.missing_core),
            ("Pistes d'animation sans bone dans le modèle", self.unmatched_tracks),
            ("Bones non reconnus (info)", self.unknown_bones),
            ("Bones optionnels absents (info)", self.missing_optional),
            ("Bones non animés (info)", self.unanimated),
        ]
        parts = [f"{title} ({len(names)}) :\n  " + ", ".join(names) for title, names in sections if names]
        return "\n\n".join(parts) or "Aucun problème détecté."


def validate(bone_names: Iterable[str], track_names: Iterable[str] | None = None) -> ValidationReport:
    bones = set(bone_names)
    tracks = set(track_names) if track_names is not None else None
    return ValidationReport(
        missing_core=sorted(MIXAMO_CORE - bones),
        unmatched_tracks=sorted(tracks - bones) if tracks is not None else [],
        unknown_bones=sorted(bones - MIXAMO_ALL),
        missing_optional=sorted(MIXAMO_OPTIONAL - bones),
        unanimated=sorted(bones - tracks) if tracks is not None else [],
    )
