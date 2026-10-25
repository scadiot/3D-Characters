"""Objets attachés aux bones d'un personnage (attachments.json) et composition du modèle."""
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from viewer.gltf_loader import LoadedFile
from viewer.mathutil import mat3_to_quat
from viewer.skeleton import Skeleton

Vec3 = tuple[float, float, float]
DEFAULT_BONE = "RightHand"


@dataclass
class Attachment:
    object: str                       # chemin relatif à Objects/
    bone: str = DEFAULT_BONE          # nom canonique
    position: Vec3 = (0.0, 0.0, 0.0)  # mètres, repère du bone sans son échelle
    rotation: Vec3 = (0.0, 0.0, 0.0)  # degrés, X puis Y puis Z
    scale: float = 1.0
    enabled: bool = True


@dataclass
class Socket:
    attachment: int    # index dans la liste d'attachements
    node: int          # nœud socket du squelette composé
    bone_scale: float  # échelle globale de repos du bone, compensée par le socket


@dataclass
class Composed:
    model: LoadedFile
    sockets: list[Socket]
    messages: list[str]


# --- configuration ---

def _vec3(value) -> Vec3:
    try:
        x, y, z = (float(v) for v in value)
        return x, y, z
    except (TypeError, ValueError):
        return 0.0, 0.0, 0.0


def _scale(value) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 1.0
    return value if value > 0 and math.isfinite(value) else 1.0


def load_attachments(path: Path) -> tuple[list[Attachment], str | None]:
    """Attachements du fichier ; le second élément décrit une erreur de lecture."""
    path = Path(path)
    if not path.is_file():
        return [], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        result = []
        for a in data.get("attachments", []):
            if not isinstance(a, dict) or not a.get("object"):
                continue
            result.append(Attachment(
                str(a["object"]),
                str(a.get("bone") or DEFAULT_BONE),
                _vec3(a.get("position")),
                _vec3(a.get("rotation")),
                _scale(a.get("scale", 1.0)),
                bool(a.get("enabled", True)),
            ))
        return result, None
    except (ValueError, AttributeError) as e:
        return [], f"{path.name} illisible : {e}"


def save_attachments(path: Path, attachments: list[Attachment]) -> None:
    data = {"attachments": [{"object": a.object, "bone": a.bone, "position": list(a.position),
                             "rotation": list(a.rotation), "scale": a.scale, "enabled": a.enabled}
                            for a in attachments]}
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def scan_objects(root: Path) -> list[str]:
    """Fichiers .glb sous `root/Objects`, en chemins relatifs avec `/`."""
    objects_dir = Path(root) / "Objects"
    if not objects_dir.is_dir():
        return []
    return sorted(p.relative_to(objects_dir).as_posix() for p in objects_dir.rglob("*")
                  if p.is_file() and p.suffix.lower() == ".glb")


# --- géométrie ---

def euler_quat(rotation: Vec3) -> np.ndarray:
    """Angles en degrés appliqués X puis Y puis Z (Rz @ Ry @ Rx) -> quaternion xyzw."""
    x, y, z = (math.radians(v) for v in rotation)
    rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rz = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return mat3_to_quat(rz @ ry @ rx)


def socket_trs(attachment: Attachment, bone_scale: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """TRS local du socket : S(1/k) @ T(position) @ R(rotation) @ S(scale), k uniforme."""
    return (np.asarray(attachment.position, np.float64) / bone_scale, euler_quat(attachment.rotation),
            np.full(3, attachment.scale / bone_scale))


def compose(model: LoadedFile, attachments: list[Attachment], objects: dict[str, LoadedFile]) -> Composed:
    """Greffe chaque objet actif sous un socket enfant de son bone ; `objects` : objets chargés par nom."""
    sk = model.skeleton
    rest = sk.global_matrices(sk.rest_pose())
    names, parents = list(sk.names), list(sk.parents)
    t, r, s = [sk.rest_t], [sk.rest_r], [sk.rest_s]
    meshes, sockets, messages = list(model.meshes), [], []
    for i, a in enumerate(attachments):
        if not a.enabled:
            continue
        obj = objects.get(a.object)
        if obj is None:
            messages.append(f"Objet introuvable ou illisible : {a.object}")
            continue
        bone = sk.index(a.bone)
        if bone is None:
            messages.append(f"{a.object} : pas de bone {a.bone} dans le squelette")
            continue
        k = float(np.linalg.norm(rest[bone][:3, :3], axis=0).mean())
        socket, prefix = len(names), f"attach{i}"
        names.append(prefix)
        parents.append(bone)
        for values, v in zip((t, r, s), socket_trs(a, k)):
            values.append(v[None])
        base, osk = len(names), obj.skeleton
        names += [f"{prefix}/{n}" for n in osk.raw_names]
        parents += [socket if p < 0 else base + int(p) for p in osk.parents]
        t.append(osk.rest_t)
        r.append(osk.rest_r)
        s.append(osk.rest_s)
        meshes += [replace(m, node=base + m.node, skin=None, material=None) for m in obj.meshes]
        sockets.append(Socket(i, socket, k))
    if not sockets:
        return Composed(model, [], messages)
    raw_names = sk.raw_names + names[len(sk.names):]
    skeleton = Skeleton(names, raw_names, np.array(parents, np.int64), np.vstack(t), np.vstack(r), np.vstack(s))
    return Composed(replace(model, skeleton=skeleton, meshes=meshes), sockets, messages)


def apply_offset(model: LoadedFile, socket: Socket, attachment: Attachment) -> None:
    """Déplace un objet déjà composé (modifie la pose de repos de son socket)."""
    sk = model.skeleton
    sk.rest_t[socket.node], sk.rest_r[socket.node], sk.rest_s[socket.node] = socket_trs(attachment,
                                                                                       socket.bone_scale)


def structure_key(attachments: list[Attachment]) -> list[tuple]:
    """Ce qui impose de recomposer le modèle (le reste se règle avec `apply_offset`)."""
    return [(a.object, a.bone, a.enabled) for a in attachments]
