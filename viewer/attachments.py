"""Objets attachés aux bones (réglage propre à chaque objet : Objects/<objet>.json) et composition du modèle."""
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from viewer.gltf_loader import LoadedFile
from viewer.mathutil import decompose, mat3_to_quat, quat_to_mat3
from viewer.skeleton import Skeleton, yaw_matrix

Vec3 = tuple[float, float, float]
DEFAULT_BONE = "RightHand"
OBJECTS_DIR = "Objects"


@dataclass
class Attachment:
    """Placement d'un objet, commun à tous les personnages.

    Repère T-pose : origine sur le bone, axes du personnage tourné vers +Z (X à sa gauche,
    Y vers le haut, Z devant lui), en mètres ; l'objet suit ensuite les rotations du bone.
    """

    object: str                       # chemin relatif à Objects/
    bone: str = DEFAULT_BONE          # nom canonique
    position: Vec3 = (0.0, 0.0, 0.0)  # mètres
    rotation: Vec3 = (0.0, 0.0, 0.0)  # degrés, X puis Y puis Z
    scale: float = 1.0


@dataclass
class Socket:
    attachment: int     # index dans la liste d'attachements
    node: int           # nœud socket du squelette composé
    basis: np.ndarray   # (4, 4) inverse de la rotation/échelle monde du bone en T-pose


@dataclass
class Composed:
    model: LoadedFile
    sockets: list[Socket]
    messages: list[str]


# --- réglages des objets ---

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


def placement_path(root: Path, name: str) -> Path:
    """Réglage d'un objet : même chemin que son .glb, extension .json."""
    return (Path(root) / OBJECTS_DIR / name).with_suffix(".json")


def load_placement(root: Path, name: str) -> tuple[Attachment, str | None]:
    """Réglage de l'objet, ou réglage par défaut ; le second élément décrit une erreur de lecture."""
    path = placement_path(root, name)
    if not path.is_file():
        return Attachment(name), None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Attachment(
            name,
            str(data.get("bone") or DEFAULT_BONE),
            _vec3(data.get("position")),
            _vec3(data.get("rotation")),
            _scale(data.get("scale", 1.0)),
        ), None
    except (ValueError, AttributeError) as e:
        return Attachment(name), f"{path.name} illisible : {e}"


def save_placement(root: Path, attachment: Attachment) -> Path:
    path = placement_path(root, attachment.object)
    data = {"bone": attachment.bone, "position": list(attachment.position),
            "rotation": list(attachment.rotation), "scale": attachment.scale}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def scan_objects(root: Path) -> list[str]:
    """Fichiers .glb sous `root/Objects`, en chemins relatifs avec `/`."""
    objects_dir = Path(root) / OBJECTS_DIR
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


def offset_matrix(attachment: Attachment) -> np.ndarray:
    """T(position) @ R(rotation) @ S(scale), dans le repère T-pose."""
    m = np.eye(4)
    m[:3, :3] = quat_to_mat3(euler_quat(attachment.rotation)) * attachment.scale
    m[:3, 3] = attachment.position
    return m


def socket_trs(attachment: Attachment, basis: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """TRS local du socket : `basis` ramène du repère du bone au repère T-pose."""
    return decompose(basis @ offset_matrix(attachment))


def compose(model: LoadedFile, attachments: list[Attachment], objects: dict[str, LoadedFile]) -> Composed:
    """Greffe chaque objet sous un socket enfant de son bone ; `objects` : objets chargés par nom."""
    sk = model.skeleton
    # Même repère que l'affichage : le Player tourne le personnage vers +Z.
    rest = yaw_matrix(-sk.facing_yaw()) @ sk.global_matrices(sk.rest_pose())
    names, parents = list(sk.names), list(sk.parents)
    t, r, s = [sk.rest_t], [sk.rest_r], [sk.rest_s]
    meshes, sockets, messages = list(model.meshes), [], []
    for i, a in enumerate(attachments):
        obj = objects.get(a.object)
        if obj is None:
            messages.append(f"Objet introuvable ou illisible : {a.object}")
            continue
        bone = sk.index(a.bone)
        if bone is None:
            messages.append(f"{a.object} : pas de bone {a.bone} dans le squelette")
            continue
        basis = np.eye(4)
        basis[:3, :3] = np.linalg.inv(rest[bone][:3, :3])
        socket, prefix = len(names), f"attach{i}"
        names.append(prefix)
        parents.append(bone)
        for values, v in zip((t, r, s), socket_trs(a, basis)):
            values.append(v[None])
        base, osk = len(names), obj.skeleton
        names += [f"{prefix}/{n}" for n in osk.raw_names]
        parents += [socket if p < 0 else base + int(p) for p in osk.parents]
        t.append(osk.rest_t)
        r.append(osk.rest_r)
        s.append(osk.rest_s)
        meshes += [replace(m, node=base + m.node, skin=None, material=None) for m in obj.meshes]
        sockets.append(Socket(i, socket, basis))
    if not sockets:
        return Composed(model, [], messages)
    raw_names = sk.raw_names + names[len(sk.names):]
    skeleton = Skeleton(names, raw_names, np.array(parents, np.int64), np.vstack(t), np.vstack(r), np.vstack(s))
    return Composed(replace(model, skeleton=skeleton, meshes=meshes), sockets, messages)


def apply_offset(model: LoadedFile, socket: Socket, attachment: Attachment) -> None:
    """Déplace un objet déjà composé (modifie la pose de repos de son socket)."""
    sk = model.skeleton
    sk.rest_t[socket.node], sk.rest_r[socket.node], sk.rest_s[socket.node] = socket_trs(attachment, socket.basis)


def structure_key(attachments: list[Attachment]) -> list[tuple]:
    """Ce qui impose de recomposer le modèle (le reste se règle avec `apply_offset`)."""
    return [(a.object, a.bone) for a in attachments]
