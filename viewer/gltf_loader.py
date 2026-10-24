"""Lecture d'un fichier .glb vers des structures numpy indépendantes de l'affichage."""
import base64
import io
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image
from pygltflib import GLTF2

from viewer.animation import AnimationClip, Track
from viewer.mathutil import decompose
from viewer.mixamo import normalize
from viewer.skeleton import Skeleton

_COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class LoadError(Exception):
    pass


@dataclass
class SkinData:
    joints: np.ndarray        # (J,) index de nœud
    inverse_bind: np.ndarray  # (J, 4, 4)


@dataclass
class MeshData:
    positions: np.ndarray  # (V, 3) float32
    normals: np.ndarray    # (V, 3) float32
    uvs: np.ndarray        # (V, 2) float32
    joints: np.ndarray     # (V, 4) int32, index dans skins[skin].joints
    weights: np.ndarray    # (V, 4) float32
    indices: np.ndarray    # (I,) uint32
    node: int
    skin: int | None
    base_color: np.ndarray  # (4,)
    texture: Image.Image | None


@dataclass
class LoadedFile:
    path: Path
    skeleton: Skeleton
    skins: list[SkinData]
    meshes: list[MeshData]
    clips: list[AnimationClip]
    infos: list[str] = field(default_factory=list)

    @property
    def skinned(self) -> bool:
        return any(m.skin is not None for m in self.meshes)

    def joint_names(self) -> set[str]:
        return {self.skeleton.names[j] for s in self.skins for j in s.joints}


def _open(path: Path) -> GLTF2:
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
    except OSError as e:
        raise LoadError(f"{path.name} : {e}") from e
    if magic != b"glTF":
        raise LoadError(f"{path.name} : ce n'est pas un fichier .glb")
    try:
        gltf = GLTF2().load(str(path))
    except Exception as e:  # pygltflib lève des exceptions variées sur un fichier invalide
        raise LoadError(f"{path.name} : {e}") from e
    if gltf is None:
        raise LoadError(f"{path.name} : fichier glTF illisible")
    return gltf


def clip_names(path: Path) -> list[str]:
    gltf = _open(Path(path))
    return [a.name or f"clip{i}" for i, a in enumerate(gltf.animations)]


def load_glb(path: Path) -> LoadedFile:
    path = Path(path)
    gltf = _open(path)
    try:
        blob = gltf.binary_blob() or b""
        infos: list[str] = []
        skeleton = _read_skeleton(gltf)
        skins = [_read_skin(gltf, blob, s) for s in gltf.skins]
        meshes = _read_meshes(gltf, blob, path.parent, infos)
        clips = [_read_clip(gltf, blob, i, skeleton) for i in range(len(gltf.animations))]
    except Exception as e:
        raise LoadError(f"{path.name} : {e}") from e
    return LoadedFile(path, skeleton, skins, meshes, clips, infos)


def read_accessor(gltf: GLTF2, blob: bytes, index: int) -> np.ndarray:
    acc = gltf.accessors[index]
    dtype = np.dtype(_COMPONENT[acc.componentType])
    width = _WIDTH[acc.type]
    if acc.bufferView is None:
        return np.zeros((acc.count, width), dtype)
    view = gltf.bufferViews[acc.bufferView]
    start = (view.byteOffset or 0) + (acc.byteOffset or 0)
    elem = dtype.itemsize * width
    stride = view.byteStride or elem
    raw = np.frombuffer(blob, np.uint8, count=stride * (acc.count - 1) + elem, offset=start)
    rows = np.lib.stride_tricks.as_strided(raw, shape=(acc.count, elem), strides=(stride, 1))
    arr = np.ascontiguousarray(rows).view(dtype).reshape(acc.count, width)
    if acc.normalized and dtype.kind in "iu":
        arr = arr.astype(np.float32) / np.iinfo(dtype).max
        if dtype.kind == "i":
            arr = np.maximum(arr, -1.0)
    return arr


def _read_skeleton(gltf: GLTF2) -> Skeleton:
    n = len(gltf.nodes)
    parents = np.full(n, -1, dtype=np.int64)
    t, r, s = np.zeros((n, 3)), np.tile([0.0, 0, 0, 1], (n, 1)), np.ones((n, 3))
    raw_names = []
    for i, node in enumerate(gltf.nodes):
        for c in node.children or []:
            parents[c] = i
        if node.matrix:
            t[i], r[i], s[i] = decompose(np.array(node.matrix, dtype=np.float64).reshape(4, 4).T)
        else:
            t[i] = node.translation or (0, 0, 0)
            r[i] = node.rotation or (0, 0, 0, 1)
            s[i] = node.scale or (1, 1, 1)
        raw_names.append(node.name or f"node{i}")
    return Skeleton([normalize(x) for x in raw_names], raw_names, parents, t, r, s)


def _read_skin(gltf, blob, skin) -> SkinData:
    joints = np.array(skin.joints, dtype=np.int64)
    if skin.inverseBindMatrices is None:
        inverse_bind = np.tile(np.eye(4), (len(joints), 1, 1))
    else:
        inverse_bind = read_accessor(gltf, blob, skin.inverseBindMatrices).astype(np.float64)
        inverse_bind = inverse_bind.reshape(-1, 4, 4).transpose(0, 2, 1)
    return SkinData(joints, inverse_bind)


def _read_meshes(gltf, blob, base_dir: Path, infos: list[str]) -> list[MeshData]:
    result = []
    for node_index, node in enumerate(gltf.nodes):
        if node.mesh is None:
            continue
        for prim in gltf.meshes[node.mesh].primitives:
            if (prim.mode if prim.mode is not None else 4) != 4:
                infos.append(f"Primitive non triangulaire ignorée (nœud {node.name})")
                continue
            a = prim.attributes
            positions = read_accessor(gltf, blob, a.POSITION).astype(np.float32)
            count = len(positions)
            if prim.indices is not None:
                indices = read_accessor(gltf, blob, prim.indices).reshape(-1).astype(np.uint32)
            else:
                indices = np.arange(count, dtype=np.uint32)
            normals = (read_accessor(gltf, blob, a.NORMAL).astype(np.float32) if a.NORMAL is not None
                       else _compute_normals(positions, indices))
            uvs = (read_accessor(gltf, blob, a.TEXCOORD_0).astype(np.float32) if a.TEXCOORD_0 is not None
                   else np.zeros((count, 2), np.float32))
            skin = node.skin if (node.skin is not None and a.JOINTS_0 is not None) else None
            if skin is not None:
                joints = read_accessor(gltf, blob, a.JOINTS_0).astype(np.int32)
                weights = read_accessor(gltf, blob, a.WEIGHTS_0).astype(np.float32)
            else:
                joints = np.zeros((count, 4), np.int32)
                weights = np.zeros((count, 4), np.float32)
            if getattr(a, "JOINTS_1", None) is not None:
                infos.append(f"JOINTS_1/WEIGHTS_1 ignorés (nœud {node.name}) : 4 influences max")
            base_color, texture = _read_material(gltf, blob, prim.material, base_dir, infos)
            result.append(MeshData(positions, normals, uvs, joints, weights, indices,
                                   node_index, skin, base_color, texture))
    return result


def _compute_normals(positions: np.ndarray, indices: np.ndarray) -> np.ndarray:
    tri = indices.reshape(-1, 3)
    p0, p1, p2 = positions[tri[:, 0]], positions[tri[:, 1]], positions[tri[:, 2]]
    face = np.cross(p1 - p0, p2 - p0)
    normals = np.zeros_like(positions)
    for k in range(3):
        np.add.at(normals, tri[:, k], face)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    return (normals / np.where(lengths > 0, lengths, 1)).astype(np.float32)


def _read_material(gltf, blob, material_index, base_dir, infos):
    base_color = np.ones(4)
    if material_index is None:
        return base_color, None
    pbr = gltf.materials[material_index].pbrMetallicRoughness
    if pbr is None:
        return base_color, None
    if pbr.baseColorFactor:
        base_color = np.array(pbr.baseColorFactor, dtype=np.float64)
    if pbr.baseColorTexture is None:
        return base_color, None
    source = gltf.textures[pbr.baseColorTexture.index].source
    if source is None:
        return base_color, None
    return base_color, _read_image(gltf, blob, source, base_dir, infos)


def _read_image(gltf, blob, image_index, base_dir: Path, infos) -> Image.Image | None:
    image = gltf.images[image_index]
    try:
        if image.bufferView is not None:
            view = gltf.bufferViews[image.bufferView]
            start = view.byteOffset or 0
            data = blob[start:start + view.byteLength]
        elif image.uri and image.uri.startswith("data:"):
            data = base64.b64decode(image.uri.split(",", 1)[1])
        elif image.uri:
            data = (base_dir / image.uri).read_bytes()
        else:
            return None
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        infos.append(f"Texture illisible : {e}")
        return None


def _read_clip(gltf, blob, index: int, skeleton: Skeleton) -> AnimationClip:
    anim = gltf.animations[index]
    rotations: dict[str, Track] = {}
    translations: dict[str, Track] = {}
    duration = 0.0
    for channel in anim.channels:
        target = channel.target
        if target.node is None or target.path not in ("rotation", "translation"):
            continue
        sampler = anim.samplers[channel.sampler]
        times = read_accessor(gltf, blob, sampler.input).reshape(-1).astype(np.float64)
        values = read_accessor(gltf, blob, sampler.output).astype(np.float64)
        interpolation = sampler.interpolation or "LINEAR"
        if interpolation == "CUBICSPLINE":  # garde les valeurs, ignore les tangentes
            values, interpolation = values[1::3], "LINEAR"
        tracks = rotations if target.path == "rotation" else translations
        tracks[skeleton.names[target.node]] = Track(times, values, interpolation)
        duration = max(duration, float(times[-1]))
    hips = skeleton.index("Hips")
    hips_rest_t = skeleton.rest_t[hips].copy() if hips is not None else None
    return AnimationClip(anim.name or f"clip{index}", duration, rotations, translations, hips_rest_t)
