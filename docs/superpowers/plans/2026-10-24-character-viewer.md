# 3D Characters Viewer — Plan d'implémentation

Spec : [2026-10-24-character-viewer-design.md](../specs/2026-10-24-character-viewer-design.md)

**But :** visualiseur de bureau PySide6 + moderngl pour personnages glTF skinnés au
squelette Mixamo, avec animations séparées et variantes de skin.

**Méthode :** TDD sur tout le cœur (sans Qt ni OpenGL), puis rendu et UI vérifiés
manuellement. Un commit par tâche.

**Ajouts par rapport à la spec (détails d'implémentation) :**
- `viewer/mathutil.py` : quaternions, matrices TRS, perspective/look-at (partagé par
  `skeleton`, `animation`, `camera`).
- `viewer/player.py` : état de lecture (modèle, clip, temps, vitesse) et calcul de la
  frame courante, sans Qt — garde `gl_view` mince et testable.
- Les GLB de test sont **générés** par `tests/glb_fixtures.py` (versionné) dans un
  dossier temporaire au lancement de pytest, au lieu de binaires versionnés.
- Règle de skin : la skin choisie remplace la texture base color des meshes qui en ont
  une ; si aucun mesh n'est texturé, elle s'applique à tous.

## Conventions communes

- Quaternions au format glTF `[x, y, z, w]`.
- Matrices numpy en convention ligne-majeure (`m @ v`), `float64` côté CPU.
  Transposées en column-major `float32` uniquement à l'envoi au GPU.
- Noms de bones toujours **canoniques** (passés par `mixamo.normalize`) dans le cœur.
- Commandes en PowerShell depuis `C:\Dev\3D-Characters`.

---

## Tâche 0 — Mise en place du projet

**Fichiers :** `pyproject.toml`, `.gitignore`, `viewer/__init__.py`, `viewer/ui/__init__.py`, `tests/conftest.py` (vide pour l'instant)

`pyproject.toml` :
```toml
[project]
name = "character-viewer"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "PySide6>=6.6",
    "moderngl>=5.10",
    "pygltflib>=1.16",
    "numpy>=1.26",
    "Pillow>=10",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
character-viewer = "viewer.main:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["viewer*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore` :
```
.venv/
__pycache__/
*.egg-info/
.pytest_cache/
```

Étapes :
1. `py -3.11 -m venv .venv` (ou la version ≥ 3.11 installée).
2. `.venv\Scripts\python -m pip install -e .[dev]`
3. `.venv\Scripts\python -m pytest` → « no tests ran » (code 5, attendu).
4. Commit : `chore: project scaffolding`.

---

## Tâche 1 — `mathutil.py`

**Fichiers :** `viewer/mathutil.py`, `tests/test_mathutil.py`

Test d'abord :
```python
import numpy as np
from viewer import mathutil as mu

def test_identity_quat_gives_identity_matrix():
    assert np.allclose(mu.quat_to_mat3([0, 0, 0, 1]), np.eye(3))

def test_quat_90_deg_about_y_maps_x_to_minus_z():
    q = mu.axis_angle_quat([0, 1, 0], np.pi / 2)
    assert np.allclose(mu.quat_to_mat3(q) @ [1, 0, 0], [0, 0, -1])

def test_slerp_halfway_is_45_degrees():
    a = [0, 0, 0, 1]
    b = mu.axis_angle_quat([0, 1, 0], np.pi / 2)
    assert np.allclose(mu.slerp(a, b, 0.5), mu.axis_angle_quat([0, 1, 0], np.pi / 4))

def test_slerp_takes_shortest_path():
    a = np.array([0, 0, 0, 1.0])
    assert np.allclose(np.abs(mu.slerp(a, -a, 0.5)), [0, 0, 0, 1])

def test_trs_decompose_round_trip():
    t, r, s = [1, 2, 3], mu.axis_angle_quat([1, 1, 0], 0.7), [2, 2, 2]
    m = mu.trs_to_mat4(np.array([t]), np.array([r]), np.array([s]))[0]
    t2, r2, s2 = mu.decompose(m)
    assert np.allclose(t2, t) and np.allclose(s2, s)
    assert np.allclose(np.abs(np.dot(r2, r)), 1.0)

def test_look_at_puts_target_on_negative_z():
    v = mu.look_at(np.array([0, 0, 5.0]), np.zeros(3), np.array([0, 1.0, 0]))
    assert np.allclose(v @ [0, 0, 0, 1], [0, 0, -5, 1])
```

Implémentation :
```python
"""Petites fonctions de géométrie : quaternions [x, y, z, w], matrices 4x4 ligne-majeure."""
import numpy as np


def axis_angle_quat(axis, angle: float) -> np.ndarray:
    axis = np.asarray(axis, dtype=np.float64)
    axis = axis / np.linalg.norm(axis)
    return np.append(axis * np.sin(angle / 2), np.cos(angle / 2))


def quat_to_mat3(q) -> np.ndarray:
    """(..., 4) -> (..., 3, 3)"""
    q = np.asarray(q, dtype=np.float64)
    x, y, z, w = np.moveaxis(q, -1, 0)
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    m = np.empty(q.shape[:-1] + (3, 3))
    m[..., 0, 0] = 1 - 2 * (yy + zz)
    m[..., 0, 1] = 2 * (xy - wz)
    m[..., 0, 2] = 2 * (xz + wy)
    m[..., 1, 0] = 2 * (xy + wz)
    m[..., 1, 1] = 1 - 2 * (xx + zz)
    m[..., 1, 2] = 2 * (yz - wx)
    m[..., 2, 0] = 2 * (xz - wy)
    m[..., 2, 1] = 2 * (yz + wx)
    m[..., 2, 2] = 1 - 2 * (xx + yy)
    return m


def mat3_to_quat(m) -> np.ndarray:
    m = np.asarray(m, dtype=np.float64)
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = np.sqrt(tr + 1) * 2
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = np.sqrt(1 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    q = np.array(q)
    return q / np.linalg.norm(q)


def trs_to_mat4(t, r, s) -> np.ndarray:
    """(N,3), (N,4), (N,3) -> (N,4,4) = T @ R @ S"""
    t = np.asarray(t, dtype=np.float64)
    m = np.zeros((t.shape[0], 4, 4))
    m[:, :3, :3] = quat_to_mat3(r) * np.asarray(s, dtype=np.float64)[:, None, :]
    m[:, :3, 3] = t
    m[:, 3, 3] = 1
    return m


def decompose(m) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Matrice 4x4 sans cisaillement -> (t, r, s)."""
    m = np.asarray(m, dtype=np.float64)
    s = np.linalg.norm(m[:3, :3], axis=0)
    return m[:3, 3].copy(), mat3_to_quat(m[:3, :3] / s), s


def slerp(a, b, u: float) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    d = np.dot(a, b)
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        q = a + u * (b - a)
        return q / np.linalg.norm(q)
    theta = np.arccos(d)
    return (np.sin((1 - u) * theta) * a + np.sin(u * theta) * b) / np.sin(theta)


def perspective(fov_y: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1 / np.tan(fov_y / 2)
    m = np.zeros((4, 4))
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2 * far * near / (near - far)
    m[3, 2] = -1
    return m


def look_at(eye, target, up) -> np.ndarray:
    f = target - eye
    f = f / np.linalg.norm(f)
    s = np.cross(f, up)
    s = s / np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[0, 3], m[1, 3], m[2, 3] = -s @ eye, -u @ eye, f @ eye
    return m
```

Étapes : test rouge → implémentation → `pytest tests/test_mathutil.py` vert → commit `feat: math helpers`.

---

## Tâche 2 — `mixamo.normalize`

**Fichiers :** `viewer/mixamo.py`, `tests/test_mixamo.py`

```python
import pytest
from viewer.mixamo import normalize

@pytest.mark.parametrize("raw", ["mixamorig:Hips", "mixamorig1:Hips", "mixamorig12:Hips", "mixamorig_Hips", "Hips"])
def test_normalize_strips_prefix(raw):
    assert normalize(raw) == "Hips"

def test_normalize_keeps_unknown_names():
    assert normalize("Armature") == "Armature"
    assert normalize("Bip01_Spine") == "Bip01_Spine"
```

```python
"""Convention de nommage des bones Mixamo."""
import re

_PREFIX = re.compile(r"^mixamorig\d*[:_]")


def normalize(name: str) -> str:
    return _PREFIX.sub("", name)
```

Commit : `feat: mixamo bone name normalization`.

---

## Tâche 3 — Générateur de GLB de test

**Fichiers :** `tests/glb_fixtures.py`, `tests/conftest.py`

Deux fichiers minuscules, aux valeurs choisies pour rendre les tests vérifiables à la main :

**tiny_model.glb** — nœuds : `0 Armature` (scale 0.01, enfant 1) → `1 mixamorig:Hips`
(t = 0,100,0, enfant 2) → `2 mixamorig:Spine` (t = 0,10,0) ; `3 Body` (mesh 0, skin 0).
Skin joints [1, 2]. Quad de 4 vertices entre y = 1 et y = 1.2 (m), les 2 du bas sur Hips,
les 2 du haut sur Spine. Texture PNG rouge 2×2 embarquée.
→ en monde : Hips à (0,1,0), Spine à (0,1.1,0).

**tiny_anim.glb** — nœuds : `0 Armature` (scale 1) → `1 mixamorig1:Hips` (t = 0,1,0) →
`2 mixamorig1:Spine` (t = 0,0.1,0) → `3 mixamorig1:Ghost`. Clip `Take 001` :
Hips translation LINEAR (0,1,0)→(0,2,0) sur [0,1] ; Spine rotation LINEAR identité→90° Y
sur [0,1] ; Ghost rotation STEP sur [0,0.5].
→ ratio Hips = 100/1 = 100 ; à t = 0.5, Hips du modèle en monde à (0,1.5,0).

`tests/glb_fixtures.py` :
```python
"""Génère les GLB minuscules utilisés par les tests."""
import io
from pathlib import Path

import numpy as np
from PIL import Image
from pygltflib import (
    GLTF2, Accessor, Animation, AnimationChannel, AnimationChannelTarget, AnimationSampler,
    Asset, Attributes, Buffer, BufferView, Material, Mesh, Node, PbrMetallicRoughness,
    Primitive, Scene, Skin, Texture, TextureInfo,
)
from pygltflib import Image as GltfImage

FLOAT, UBYTE, USHORT = 5126, 5121, 5123


class _Builder:
    def __init__(self):
        self.gltf = GLTF2(asset=Asset(version="2.0"), scene=0)
        self.data = bytearray()

    def view(self, raw: bytes) -> int:
        while len(self.data) % 4:
            self.data.append(0)
        self.gltf.bufferViews.append(BufferView(buffer=0, byteOffset=len(self.data), byteLength=len(raw)))
        self.data += raw
        return len(self.gltf.bufferViews) - 1

    def accessor(self, arr: np.ndarray, gl_type: str, component: int, minmax: bool = False) -> int:
        kw = {}
        if minmax:
            kw = {"min": np.atleast_1d(arr.min(axis=0)).tolist(), "max": np.atleast_1d(arr.max(axis=0)).tolist()}
        self.gltf.accessors.append(
            Accessor(bufferView=self.view(arr.tobytes()), componentType=component, count=len(arr), type=gl_type, **kw)
        )
        return len(self.gltf.accessors) - 1

    def save(self, path: Path) -> None:
        self.gltf.buffers = [Buffer(byteLength=len(self.data))]
        self.gltf.set_binary_blob(bytes(self.data))
        self.gltf.save_binary(str(path))


def _translation(x, y, z) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def build_model(path: Path) -> None:
    b = _Builder()
    g = b.gltf
    g.nodes = [
        Node(name="Armature", scale=[0.01, 0.01, 0.01], children=[1]),
        Node(name="mixamorig:Hips", translation=[0, 100, 0], children=[2]),
        Node(name="mixamorig:Spine", translation=[0, 10, 0]),
        Node(name="Body", mesh=0, skin=0),
    ]
    g.scenes = [Scene(nodes=[0, 3])]

    hips = np.diag([0.01, 0.01, 0.01, 1.0]) @ _translation(0, 100, 0)
    spine = hips @ _translation(0, 10, 0)
    inverse_bind = np.stack([np.linalg.inv(hips).T, np.linalg.inv(spine).T]).astype(np.float32)  # column-major
    g.skins = [Skin(joints=[1, 2], inverseBindMatrices=b.accessor(inverse_bind.reshape(2, 16), "MAT4", FLOAT))]

    positions = np.array([[-0.1, 1, 0], [0.1, 1, 0], [0.1, 1.2, 0], [-0.1, 1.2, 0]], np.float32)
    normals = np.tile(np.array([[0, 0, 1]], np.float32), (4, 1))
    uvs = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], np.float32)
    joints = np.array([[0, 0, 0, 0], [0, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]], np.uint8)
    weights = np.array([[1, 0, 0, 0]] * 4, np.float32)
    indices = np.array([0, 1, 2, 0, 2, 3], np.uint16)
    attributes = Attributes(
        POSITION=b.accessor(positions, "VEC3", FLOAT, minmax=True),
        NORMAL=b.accessor(normals, "VEC3", FLOAT),
        TEXCOORD_0=b.accessor(uvs, "VEC2", FLOAT),
        JOINTS_0=b.accessor(joints, "VEC4", UBYTE),
        WEIGHTS_0=b.accessor(weights, "VEC4", FLOAT),
    )
    g.meshes = [Mesh(name="Body", primitives=[
        Primitive(attributes=attributes, indices=b.accessor(indices, "SCALAR", USHORT), material=0)
    ])]

    png = io.BytesIO()
    Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(png, format="PNG")
    g.images = [GltfImage(bufferView=b.view(png.getvalue()), mimeType="image/png")]
    g.textures = [Texture(source=0)]
    g.materials = [Material(name="Skin", pbrMetallicRoughness=PbrMetallicRoughness(baseColorTexture=TextureInfo(index=0)))]
    b.save(path)


def build_anim(path: Path) -> None:
    b = _Builder()
    g = b.gltf
    g.nodes = [
        Node(name="Armature", children=[1]),
        Node(name="mixamorig1:Hips", translation=[0, 1, 0], children=[2]),
        Node(name="mixamorig1:Spine", translation=[0, 0.1, 0], children=[3]),
        Node(name="mixamorig1:Ghost"),
    ]
    g.scenes = [Scene(nodes=[0])]

    def sampler(times, values, gl_type, interpolation):
        return AnimationSampler(
            input=b.accessor(np.array(times, np.float32), "SCALAR", FLOAT, minmax=True),
            output=b.accessor(np.array(values, np.float32), gl_type, FLOAT),
            interpolation=interpolation,
        )

    s = float(np.sqrt(0.5))
    g.animations = [Animation(
        name="Take 001",
        samplers=[
            sampler([0, 1], [[0, 1, 0], [0, 2, 0]], "VEC3", "LINEAR"),
            sampler([0, 1], [[0, 0, 0, 1], [0, s, 0, s]], "VEC4", "LINEAR"),
            sampler([0, 0.5], [[0, 0, 0, 1], [0, 0, 0, 1]], "VEC4", "STEP"),
        ],
        channels=[
            AnimationChannel(sampler=0, target=AnimationChannelTarget(node=1, path="translation")),
            AnimationChannel(sampler=1, target=AnimationChannelTarget(node=2, path="rotation")),
            AnimationChannel(sampler=2, target=AnimationChannelTarget(node=3, path="rotation")),
        ],
    )]
    b.save(path)
```

`tests/conftest.py` :
```python
import pytest

import glb_fixtures


@pytest.fixture(scope="session")
def glb_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("glb")
    glb_fixtures.build_model(d / "tiny_model.glb")
    glb_fixtures.build_anim(d / "tiny_anim.glb")
    return d


@pytest.fixture(scope="session")
def model_path(glb_dir):
    return glb_dir / "tiny_model.glb"


@pytest.fixture(scope="session")
def anim_path(glb_dir):
    return glb_dir / "tiny_anim.glb"
```

Vérification : ajouter temporairement un test `assert model_path.stat().st_size > 0` ou
lancer `pytest -q` (les fixtures ne sont construites qu'à l'usage — validé en tâche 4).
Commit : `test: generated glb fixtures`.

---

## Tâche 4 — `skeleton.py` + `gltf_loader.py` (lecture)

Les deux arrivent ensemble : le loader produit le `Skeleton`.

**Fichiers :** `viewer/skeleton.py`, `viewer/gltf_loader.py`, `viewer/animation.py`
(seulement les dataclasses `Track`/`AnimationClip` à ce stade), `tests/test_loader.py`, `tests/test_skeleton.py`

Tests `tests/test_loader.py` :
```python
import numpy as np
import pytest
from viewer.gltf_loader import LoadError, clip_names, load_glb

def test_model_skeleton_names_are_canonical(model_path):
    f = load_glb(model_path)
    assert f.skeleton.names == ["Armature", "Hips", "Spine", "Body"]
    assert f.skeleton.raw_names[1] == "mixamorig:Hips"
    assert f.skeleton.parents.tolist() == [-1, 0, 1, -1]

def test_model_skin_and_mesh(model_path):
    f = load_glb(model_path)
    assert f.skinned
    assert f.skins[0].joints.tolist() == [1, 2]
    assert f.joint_names() == {"Hips", "Spine"}
    m = f.meshes[0]
    assert m.positions.shape == (4, 3) and m.indices.tolist() == [0, 1, 2, 0, 2, 3]
    assert m.joints.dtype == np.int32 and m.joints[:, 0].tolist() == [0, 0, 1, 1]
    assert m.skin == 0 and m.node == 3
    assert m.texture is not None and m.texture.size == (2, 2)
    assert f.clips == []

def test_anim_clip(anim_path):
    clip = load_glb(anim_path).clips[0]
    assert clip.name == "Take 001"
    assert clip.duration == pytest.approx(1.0)
    assert set(clip.rotations) == {"Spine", "Ghost"}
    assert set(clip.translations) == {"Hips"}
    assert clip.rotations["Ghost"].interpolation == "STEP"
    assert np.allclose(clip.hips_rest_t, [0, 1, 0])
    assert clip.track_names() == {"Hips", "Spine", "Ghost"}

def test_clip_names(anim_path, model_path):
    assert clip_names(anim_path) == ["Take 001"]
    assert clip_names(model_path) == []

def test_corrupt_file_raises_load_error(tmp_path):
    bad = tmp_path / "bad.glb"
    bad.write_bytes(b"not a glb at all")
    with pytest.raises(LoadError):
        load_glb(bad)
```

Tests `tests/test_skeleton.py` :
```python
import numpy as np
from viewer.gltf_loader import load_glb

def test_rest_pose_times_inverse_bind_is_identity(model_path):
    f = load_glb(model_path)
    g = f.skeleton.global_matrices(f.skeleton.rest_pose())
    skin = f.skins[0]
    for m in g[skin.joints] @ skin.inverse_bind:
        assert np.allclose(m, np.eye(4), atol=1e-6)

def test_global_positions(model_path):
    f = load_glb(model_path)
    g = f.skeleton.global_matrices(f.skeleton.rest_pose())
    assert np.allclose(g[1][:3, 3], [0, 1, 0])
    assert np.allclose(g[2][:3, 3], [0, 1.1, 0])

def test_index_lookup(model_path):
    sk = load_glb(model_path).skeleton
    assert sk.index("Spine") == 2 and sk.index("Nope") is None
```

`viewer/skeleton.py` :
```python
"""Hiérarchie de nœuds et calcul des matrices globales."""
from dataclasses import dataclass, field

import numpy as np

from viewer.mathutil import trs_to_mat4


@dataclass
class Pose:
    t: np.ndarray  # (N, 3)
    r: np.ndarray  # (N, 4) xyzw
    s: np.ndarray  # (N, 3)


@dataclass
class Skeleton:
    names: list[str]       # canoniques
    raw_names: list[str]
    parents: np.ndarray    # (N,) int, -1 = racine
    rest_t: np.ndarray
    rest_r: np.ndarray
    rest_s: np.ndarray
    order: list[int] = field(init=False)
    _index: dict[str, int] = field(init=False, repr=False)

    def __post_init__(self):
        self._index = {}
        for i, name in enumerate(self.names):
            self._index.setdefault(name, i)
        self.order = _parents_first(self.parents)

    def index(self, name: str) -> int | None:
        return self._index.get(name)

    def rest_pose(self) -> Pose:
        return Pose(self.rest_t.copy(), self.rest_r.copy(), self.rest_s.copy())

    def global_matrices(self, pose: Pose) -> np.ndarray:
        local = trs_to_mat4(pose.t, pose.r, pose.s)
        result = np.empty_like(local)
        for i in self.order:
            p = self.parents[i]
            result[i] = local[i] if p < 0 else result[p] @ local[i]
        return result


def _parents_first(parents: np.ndarray) -> list[int]:
    order, done = [], set()

    def visit(i: int) -> None:
        if i in done:
            return
        if parents[i] >= 0:
            visit(int(parents[i]))
        done.add(i)
        order.append(i)

    for i in range(len(parents)):
        visit(i)
    return order
```

`viewer/animation.py` (partie données, complétée en tâche 5) :
```python
"""Clips d'animation indexés par nom de bone canonique."""
from dataclasses import dataclass

import numpy as np


@dataclass
class Track:
    times: np.ndarray        # (K,)
    values: np.ndarray       # (K, 3) translation ou (K, 4) rotation
    interpolation: str       # "LINEAR" | "STEP"


@dataclass
class AnimationClip:
    name: str
    duration: float
    rotations: dict[str, Track]
    translations: dict[str, Track]
    hips_rest_t: np.ndarray | None  # translation locale de repos des Hips dans le fichier d'animation

    def track_names(self) -> set[str]:
        return set(self.rotations) | set(self.translations)
```

`viewer/gltf_loader.py` :
```python
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
        gltf = GLTF2().load(str(path))
    except Exception as e:  # pygltflib lève des exceptions variées sur un fichier invalide
        raise LoadError(f"{path.name} : {e}") from e
    if gltf is None:
        raise LoadError(f"{path.name} : fichier glTF illisible")
    return gltf


def clip_names(path: Path) -> list[str]:
    gltf = _open(path)
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
    except LoadError:
        raise
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
```

Étapes : tests rouges → implémentation → `pytest` vert → commit `feat: glb loader and skeleton`.

Point d'attention : si `test_corrupt_file_raises_load_error` échoue parce que pygltflib
renvoie un objet vide au lieu de lever, ajouter dans `_open` : lever `LoadError` si
`gltf.asset` est absent ou si le fichier ne commence pas par `b"glTF"` (vérifier les 4
premiers octets avant d'appeler pygltflib).

---

## Tâche 5 — Échantillonnage et application des animations

**Fichiers :** `viewer/animation.py` (compléter), `tests/test_animation.py`

```python
import numpy as np
import pytest
from viewer import mathutil as mu
from viewer.animation import Track, apply_clip, hips_ratio, loop_time, sample_track
from viewer.gltf_loader import load_glb

LIN = Track(np.array([0.0, 1.0]), np.array([[0, 1, 0], [0, 2, 0.0]]), "LINEAR")

@pytest.mark.parametrize("t,expected", [(0, 1), (0.5, 1.5), (1, 2), (-1, 1), (5, 2)])
def test_linear_translation(t, expected):
    assert np.allclose(sample_track(LIN, t), [0, expected, 0])

def test_step():
    tr = Track(np.array([0.0, 0.5]), np.array([[0, 0, 0.0], [1, 1, 1.0]]), "STEP")
    assert np.allclose(sample_track(tr, 0.49), [0, 0, 0])
    assert np.allclose(sample_track(tr, 0.5), [1, 1, 1])

def test_rotation_uses_slerp():
    q90 = mu.axis_angle_quat([0, 1, 0], np.pi / 2)
    tr = Track(np.array([0.0, 1.0]), np.array([[0, 0, 0, 1.0], q90]), "LINEAR")
    assert np.allclose(sample_track(tr, 0.5), mu.axis_angle_quat([0, 1, 0], np.pi / 4))

def test_loop_time():
    assert loop_time(2.5, 1.0) == pytest.approx(0.5)
    assert loop_time(3.0, 0.0) == 0.0

def test_hips_ratio(model_path, anim_path):
    model, clip = load_glb(model_path), load_glb(anim_path).clips[0]
    assert hips_ratio(model.skeleton, clip) == pytest.approx(100)

def test_apply_clip(model_path, anim_path):
    model, clip = load_glb(model_path), load_glb(anim_path).clips[0]
    sk = model.skeleton
    pose = sk.rest_pose()
    apply_clip(clip, sk, pose, 0.5, hips_ratio(sk, clip))
    assert np.allclose(pose.t[sk.index("Hips")], [0, 150, 0])          # translation Hips mise à l'échelle
    assert np.allclose(pose.t[sk.index("Spine")], [0, 10, 0])          # translation de repos conservée
    assert np.allclose(pose.r[sk.index("Spine")], mu.axis_angle_quat([0, 1, 0], np.pi / 4))
    g = sk.global_matrices(pose)
    assert np.allclose(g[sk.index("Hips")][:3, 3], [0, 1.5, 0])
```

À ajouter dans `viewer/animation.py` :
```python
from viewer.mathutil import slerp
from viewer.skeleton import Pose, Skeleton


def loop_time(t: float, duration: float) -> float:
    return float(t % duration) if duration > 0 else 0.0


def sample_track(track: Track, t: float) -> np.ndarray:
    times, values = track.times, track.values
    if t <= times[0]:
        return values[0].copy()
    if t >= times[-1]:
        return values[-1].copy()
    k = int(np.searchsorted(times, t, side="right")) - 1
    if track.interpolation == "STEP":
        return values[k].copy()
    u = (t - times[k]) / (times[k + 1] - times[k])
    if values.shape[1] == 4:
        return slerp(values[k], values[k + 1], u)
    return values[k] + u * (values[k + 1] - values[k])


def hips_ratio(skeleton: Skeleton, clip: AnimationClip) -> float:
    """Rapport d'échelle entre les Hips de repos du modèle et celles de l'animation (cm/m)."""
    i = skeleton.index("Hips")
    if i is None or clip.hips_rest_t is None:
        return 1.0
    anim_length = np.linalg.norm(clip.hips_rest_t)
    return float(np.linalg.norm(skeleton.rest_t[i]) / anim_length) if anim_length > 1e-8 else 1.0


def apply_clip(clip: AnimationClip, skeleton: Skeleton, pose: Pose, t: float, ratio: float) -> None:
    """Écrit dans `pose` : rotations de tous les bones appariés, translation des Hips seulement."""
    for name, track in clip.rotations.items():
        i = skeleton.index(name)
        if i is not None:
            pose.r[i] = sample_track(track, t)
    hips_track = clip.translations.get("Hips")
    i = skeleton.index("Hips")
    if hips_track is not None and i is not None:
        pose.t[i] = sample_track(hips_track, t) * ratio
```

Note : le ratio utilise la norme de la translation locale de repos (la « hauteur » des Hips
dans l'espace de leur parent), robuste même si l'axe vertical n'est pas Y.

Commit : `feat: animation sampling and retarget-by-name`.

---

## Tâche 6 — `mixamo.validate`

**Fichiers :** `viewer/mixamo.py` (compléter), `tests/test_mixamo.py` (compléter)

```python
from viewer.gltf_loader import load_glb
from viewer.mixamo import validate

def test_validate_explicit_names():
    r = validate({"Hips", "Spine", "Foo"}, {"Hips", "Bar"})
    assert "Spine1" in r.missing_core and "LeftHandIndex1" in r.missing_optional
    assert r.unknown_bones == ["Foo"]
    assert r.unmatched_tracks == ["Bar"]
    assert r.unanimated == ["Foo", "Spine"]
    assert r.warnings == len(r.missing_core) + 1 and not r.ok

def test_validate_without_clip():
    r = validate({"Hips"})
    assert r.unmatched_tracks == [] and r.unanimated == []

def test_validate_fixtures(model_path, anim_path):
    model, clip = load_glb(model_path), load_glb(anim_path).clips[0]
    r = validate(model.joint_names(), clip.track_names())
    assert r.unmatched_tracks == ["Ghost"] and r.unanimated == []

def test_details_text():
    assert "Ghost" in validate({"Hips"}, {"Ghost"}).details()
```

```python
from dataclasses import dataclass
from typing import Iterable

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
```

Commit : `feat: mixamo skeleton validation report`.

---

## Tâche 7 — `player.py`

**Fichiers :** `viewer/player.py`, `tests/test_player.py`

```python
import numpy as np
import pytest
from viewer.gltf_loader import load_glb
from viewer.player import Player

@pytest.fixture
def player(model_path, anim_path):
    p = Player()
    p.set_model(load_glb(model_path))
    p.set_clip(load_glb(anim_path).clips[0])
    return p

def test_no_model_no_frame():
    assert Player().frame() is None

def test_frame_at_half(player):
    player.seek(0.5)
    f = player.frame()
    assert np.allclose(f.globals[1][:3, 3], [0, 1.5, 0])
    assert len(f.joint_matrices) == 1 and f.joint_matrices[0].shape == (2, 4, 4)

def test_advance_loops_and_respects_speed(player):
    player.speed = 2.0
    player.advance(0.75)
    assert player.time == pytest.approx(0.5)

def test_pause_and_seek_clamp(player):
    player.playing = False
    player.advance(0.3)
    assert player.time == 0
    player.seek(10)
    assert player.time == pytest.approx(1.0)

def test_without_clip_is_rest_pose(model_path):
    p = Player()
    p.set_model(load_glb(model_path))
    assert np.allclose(p.frame().joint_matrices[0], np.eye(4), atol=1e-6)

def test_bone_segments(model_path):
    p = Player()
    p.set_model(load_glb(model_path))
    segs = p.bone_segments(p.frame())
    assert segs.shape == (1, 2, 3)
    assert np.allclose(segs[0], [[0, 1, 0], [0, 1.1, 0]])

def test_bounds(model_path):
    p = Player()
    p.set_model(load_glb(model_path))
    lo, hi = p.bounds()
    assert np.allclose(lo, [-0.1, 1, 0]) and np.allclose(hi, [0.1, 1.2, 0])
```

```python
"""État de lecture et calcul de la frame courante (sans Qt)."""
from dataclasses import dataclass

import numpy as np

from viewer.animation import AnimationClip, apply_clip, hips_ratio, loop_time
from viewer.gltf_loader import LoadedFile


@dataclass
class FrameData:
    globals: np.ndarray               # (N, 4, 4) par nœud
    joint_matrices: list[np.ndarray]  # par skin : (J, 4, 4)


class Player:
    def __init__(self):
        self.model: LoadedFile | None = None
        self.clip: AnimationClip | None = None
        self.time = 0.0
        self.speed = 1.0
        self.playing = True
        self._ratio = 1.0

    @property
    def duration(self) -> float:
        return self.clip.duration if self.clip else 0.0

    def set_model(self, model: LoadedFile | None) -> None:
        self.model = model
        self._update_ratio()

    def set_clip(self, clip: AnimationClip | None) -> None:
        self.clip = clip
        self.time = 0.0
        self._update_ratio()

    def _update_ratio(self) -> None:
        if self.model and self.clip:
            self._ratio = hips_ratio(self.model.skeleton, self.clip)
        else:
            self._ratio = 1.0

    def advance(self, dt: float) -> None:
        if self.playing and self.duration > 0:
            self.time = loop_time(self.time + dt * self.speed, self.duration)

    def seek(self, t: float) -> None:
        self.time = min(max(t, 0.0), self.duration)

    def frame(self) -> FrameData | None:
        if self.model is None:
            return None
        sk = self.model.skeleton
        pose = sk.rest_pose()
        if self.clip is not None:
            apply_clip(self.clip, sk, pose, self.time, self._ratio)
        g = sk.global_matrices(pose)
        return FrameData(g, [g[s.joints] @ s.inverse_bind for s in self.model.skins])

    def bone_segments(self, frame: FrameData | None) -> np.ndarray:
        if self.model is None or frame is None or not self.model.skins:
            return np.zeros((0, 2, 3), np.float32)
        joints = self.model.skins[0].joints
        joint_set = set(joints.tolist())
        parents = self.model.skeleton.parents
        segs = [(frame.globals[parents[j]][:3, 3], frame.globals[j][:3, 3])
                for j in joints if parents[j] in joint_set]
        return np.array(segs, np.float32).reshape(-1, 2, 3)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        if self.model is None or not self.model.meshes:
            return np.array([-1.0, 0, -1]), np.array([1.0, 2, 1])
        g = self.model.skeleton.global_matrices(self.model.skeleton.rest_pose())
        points = []
        for m in self.model.meshes:
            p = m.positions.astype(np.float64)
            if m.skin is None:
                p = p @ g[m.node][:3, :3].T + g[m.node][:3, 3]
            points.append(p)
        allp = np.concatenate(points)
        return allp.min(axis=0), allp.max(axis=0)
```

Note : en pose de repos, les positions de bind d'un mesh skinné sont déjà en espace monde
(joint × inverse bind ≈ identité), d'où l'usage direct de `positions` pour les bornes.

Commit : `feat: playback state and frame computation`.

---

## Tâche 8 — `library.py`

**Fichiers :** `viewer/library.py`, `tests/test_library.py`

```python
import shutil
from viewer import library
from viewer.library import scan

def _tree(root, model_path, anim_path):
    soldat = root / "Characters" / "soldat"
    (soldat / "skins").mkdir(parents=True)
    shutil.copy(model_path, soldat / "soldat.glb")
    (soldat / "skins" / "rouge.png").write_bytes(b"x")
    (soldat / "skins" / "bleu.jpg").write_bytes(b"x")
    (soldat / "skins" / "notes.txt").write_bytes(b"x")
    zombie = root / "Characters" / "zombie"
    zombie.mkdir()
    shutil.copy(model_path, zombie / "other.glb")
    (root / "Characters" / "empty").mkdir()
    (root / "Animations").mkdir()
    shutil.copy(anim_path, root / "Animations" / "run.glb")
    (root / "Animations" / "broken.glb").write_bytes(b"garbage")

def test_scan(tmp_path, model_path, anim_path):
    _tree(tmp_path, model_path, anim_path)
    lib = scan(tmp_path)
    assert [c.name for c in lib.characters] == ["soldat", "zombie"]
    assert [p.name for p in lib.characters[0].skins] == ["bleu.jpg", "rouge.png"]
    assert lib.characters[1].model_path.name == "other.glb"
    assert [a.label for a in lib.animations] == ["broken", "run"]
    assert lib.animations[0].error and lib.animations[1].error is None
    assert any("empty" in m for m in lib.messages)

def test_multi_clip_labels(tmp_path, monkeypatch):
    (tmp_path / "Characters").mkdir()
    (tmp_path / "Animations").mkdir()
    (tmp_path / "Animations" / "pack.glb").write_bytes(b"x")
    monkeypatch.setattr(library, "clip_names", lambda p: ["Idle", "Walk"])
    lib = scan(tmp_path)
    assert [(a.label, a.clip_index) for a in lib.animations] == [("pack / Idle", 0), ("pack / Walk", 1)]

def test_missing_folders(tmp_path):
    lib = scan(tmp_path)
    assert lib.characters == [] and lib.animations == [] and len(lib.messages) == 2
```

```python
"""Découverte des personnages, skins et animations sous un dossier racine."""
from dataclasses import dataclass, field
from pathlib import Path

from viewer.gltf_loader import LoadError, clip_names

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


@dataclass
class CharacterEntry:
    name: str
    model_path: Path
    skins: list[Path]


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
            lib.characters.append(CharacterEntry(d.name, model, _find_skins(d / "skins")))
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
    return sorted(p for p in d.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


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
```

Commit : `feat: character library scanning`.

---

## Tâche 9 — `camera.py`

**Fichiers :** `viewer/camera.py`, `tests/test_camera.py`

```python
import numpy as np
from viewer.camera import OrbitCamera

def test_eye_position():
    c = OrbitCamera()
    c.yaw, c.pitch, c.distance, c.target = 0.0, 0.0, 4.0, np.zeros(3)
    assert np.allclose(c.eye(), [0, 0, 4])

def test_pitch_is_clamped():
    c = OrbitCamera()
    c.rotate(0, 100000)
    assert c.pitch < np.pi / 2

def test_zoom_in_reduces_distance():
    c = OrbitCamera()
    d = c.distance
    c.zoom(1)
    assert c.distance < d

def test_frame_centers_target():
    c = OrbitCamera()
    c.frame(np.array([-1.0, 0, -1]), np.array([1.0, 2, 1]))
    assert np.allclose(c.target, [0, 1, 0]) and c.distance > np.sqrt(3)

def test_view_maps_target_in_front():
    c = OrbitCamera()
    v = c.view() @ np.append(c.target, 1)
    assert np.allclose(v[:3], [0, 0, -c.distance])
```

```python
"""Caméra orbitale autour d'une cible."""
import numpy as np

from viewer.mathutil import look_at, perspective

_UP = np.array([0.0, 1.0, 0.0])
_ROTATE_SPEED = 0.01  # radians par pixel
_PITCH_LIMIT = np.radians(89)


class OrbitCamera:
    def __init__(self):
        self.yaw = 0.0
        self.pitch = 0.2
        self.distance = 3.0
        self.target = np.array([0.0, 1.0, 0.0])
        self.fov_y = np.radians(45)

    def eye(self) -> np.ndarray:
        cp = np.cos(self.pitch)
        offset = np.array([cp * np.sin(self.yaw), np.sin(self.pitch), cp * np.cos(self.yaw)])
        return self.target + self.distance * offset

    def rotate(self, dx: float, dy: float) -> None:
        self.yaw -= dx * _ROTATE_SPEED
        self.pitch = float(np.clip(self.pitch + dy * _ROTATE_SPEED, -_PITCH_LIMIT, _PITCH_LIMIT))

    def zoom(self, steps: float) -> None:
        self.distance = max(self.distance * 0.9 ** steps, 0.01)

    def pan(self, dx: float, dy: float, viewport_height: float) -> None:
        forward = self.target - self.eye()
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, _UP)
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        per_pixel = 2 * self.distance * np.tan(self.fov_y / 2) / max(viewport_height, 1)
        self.target = self.target + (-dx * right + dy * up) * per_pixel

    def frame(self, lo: np.ndarray, hi: np.ndarray) -> None:
        self.target = (lo + hi) / 2
        radius = max(np.linalg.norm(hi - lo) / 2, 1e-3)
        self.distance = radius / np.sin(self.fov_y / 2) * 1.1

    def view(self) -> np.ndarray:
        return look_at(self.eye(), self.target, _UP)

    def projection(self, aspect: float) -> np.ndarray:
        return perspective(self.fov_y, aspect, self.distance * 0.01, self.distance * 100)
```

Commit : `feat: orbit camera`.

---

## Tâche 10 — `renderer.py` (vérification manuelle)

**Fichiers :** `viewer/renderer.py`

Pas de test unitaire (nécessite un contexte GL) ; vérifié en tâche 12.

```python
"""Rendu moderngl : mesh skinné, grille au sol, bones en lignes."""
import moderngl
import numpy as np
from PIL import Image

from viewer.gltf_loader import LoadedFile
from viewer.player import FrameData

MAX_BONES = 128

MESH_VS = """
#version 330
layout(std140) uniform Bones { mat4 u_bones[128]; };
uniform mat4 u_view_proj;
uniform mat4 u_model;
uniform int u_skinned;
in vec3 in_position;
in vec3 in_normal;
in vec2 in_uv;
in ivec4 in_joints;
in vec4 in_weights;
out vec3 v_normal;
out vec2 v_uv;
void main() {
    mat4 m = u_model;
    if (u_skinned == 1) {
        m = in_weights.x * u_bones[in_joints.x] + in_weights.y * u_bones[in_joints.y]
          + in_weights.z * u_bones[in_joints.z] + in_weights.w * u_bones[in_joints.w];
    }
    v_normal = mat3(m) * in_normal;
    v_uv = in_uv;
    gl_Position = u_view_proj * m * vec4(in_position, 1.0);
}
"""

MESH_FS = """
#version 330
uniform sampler2D u_tex;
uniform vec4 u_base_color;
uniform vec3 u_light_dir;
in vec3 v_normal;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec4 albedo = texture(u_tex, v_uv) * u_base_color;
    float diffuse = max(dot(normalize(v_normal), -u_light_dir), 0.0);
    f_color = vec4(albedo.rgb * (0.35 + 0.65 * diffuse), albedo.a);
}
"""

LINE_VS = """
#version 330
uniform mat4 u_view_proj;
in vec3 in_position;
void main() { gl_Position = u_view_proj * vec4(in_position, 1.0); }
"""

LINE_FS = """
#version 330
uniform vec3 u_color;
out vec4 f_color;
void main() { f_color = vec4(u_color, 1.0); }
"""


def _gl_mat(m: np.ndarray) -> bytes:
    return np.ascontiguousarray(m.T, dtype="f4").tobytes()


def _gl_mats(ms: np.ndarray) -> bytes:
    return np.ascontiguousarray(ms.transpose(0, 2, 1), dtype="f4").tobytes()


class _GpuMesh:
    def __init__(self, vao, buffers, texture, base_color, skin, node):
        self.vao, self.buffers, self.texture = vao, buffers, texture
        self.base_color, self.skin, self.node = base_color, skin, node

    def release(self):
        self.vao.release()
        for b in self.buffers:
            b.release()
        if self.texture:
            self.texture.release()


class Renderer:
    def __init__(self, ctx: moderngl.Context):
        self.ctx = ctx
        self.mesh_prog = ctx.program(vertex_shader=MESH_VS, fragment_shader=MESH_FS)
        self.line_prog = ctx.program(vertex_shader=LINE_VS, fragment_shader=LINE_FS)
        self.mesh_prog["Bones"].binding = 0
        self.bones_ubo = ctx.buffer(reserve=MAX_BONES * 64)
        self.white = ctx.texture((1, 1), 4, b"\xff\xff\xff\xff")
        self.meshes: list[_GpuMesh] = []
        self.skin_texture = None
        self._any_textured = False
        grid = self._grid_vertices()
        self.grid_vbo = ctx.buffer(grid.tobytes())
        self.grid_vao = ctx.vertex_array(self.line_prog, [(self.grid_vbo, "3f", "in_position")])
        self.bones_vbo = ctx.buffer(reserve=MAX_BONES * 2 * 12)
        self.bones_vao = ctx.vertex_array(self.line_prog, [(self.bones_vbo, "3f", "in_position")])

    @staticmethod
    def _grid_vertices() -> np.ndarray:
        lines = []
        for v in np.arange(-5, 5.01, 0.5):
            lines += [(v, 0, -5), (v, 0, 5), (-5, 0, v), (5, 0, v)]
        return np.array(lines, dtype="f4")

    def _texture(self, image: Image.Image):
        image = image.convert("RGBA")
        tex = self.ctx.texture(image.size, 4, image.tobytes())
        tex.build_mipmaps()
        tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        return tex

    def set_model(self, model: LoadedFile | None) -> None:
        for m in self.meshes:
            m.release()
        self.meshes = []
        if model is None:
            return
        for m in model.meshes:
            buffers = [
                self.ctx.buffer(m.positions.astype("f4").tobytes()),
                self.ctx.buffer(m.normals.astype("f4").tobytes()),
                self.ctx.buffer(m.uvs.astype("f4").tobytes()),
                self.ctx.buffer(m.joints.astype("i4").tobytes()),
                self.ctx.buffer(m.weights.astype("f4").tobytes()),
            ]
            index = self.ctx.buffer(m.indices.astype("u4").tobytes())
            vao = self.ctx.vertex_array(self.mesh_prog, [
                (buffers[0], "3f", "in_position"),
                (buffers[1], "3f", "in_normal"),
                (buffers[2], "2f", "in_uv"),
                (buffers[3], "4i", "in_joints"),
                (buffers[4], "4f", "in_weights"),
            ], index_buffer=index, index_element_size=4)
            texture = self._texture(m.texture) if m.texture is not None else None
            self.meshes.append(_GpuMesh(vao, buffers + [index], texture,
                                        tuple(float(x) for x in m.base_color), m.skin, m.node))
        self._any_textured = any(m.texture is not None for m in self.meshes)

    def set_skin(self, image: Image.Image | None) -> None:
        if self.skin_texture:
            self.skin_texture.release()
        self.skin_texture = self._texture(image) if image is not None else None

    def render(self, fbo, view_proj: np.ndarray, frame: FrameData | None, bone_segments: np.ndarray | None) -> None:
        fbo.use()
        fbo.clear(0.18, 0.19, 0.21, 1.0, depth=1.0)
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.disable(moderngl.CULL_FACE)
        vp = _gl_mat(view_proj)

        self.line_prog["u_view_proj"].write(vp)
        self.line_prog["u_color"].value = (0.32, 0.33, 0.36)
        self.grid_vao.render(moderngl.LINES)

        if frame is not None:
            light = np.array([-0.4, -1.0, -0.6])
            self.mesh_prog["u_view_proj"].write(vp)
            self.mesh_prog["u_light_dir"].value = tuple(light / np.linalg.norm(light))
            self.mesh_prog["u_tex"].value = 0
            self.bones_ubo.bind_to_uniform_block(0)
            for m in self.meshes:
                if m.skin is not None:
                    self.bones_ubo.write(_gl_mats(frame.joint_matrices[m.skin][:MAX_BONES]))
                    self.mesh_prog["u_skinned"].value = 1
                    self.mesh_prog["u_model"].write(_gl_mat(np.eye(4)))
                else:
                    self.mesh_prog["u_skinned"].value = 0
                    self.mesh_prog["u_model"].write(_gl_mat(frame.globals[m.node]))
                use_skin = self.skin_texture is not None and (m.texture is not None or not self._any_textured)
                (self.skin_texture if use_skin else (m.texture or self.white)).use(0)
                self.mesh_prog["u_base_color"].value = m.base_color
                m.vao.render(moderngl.TRIANGLES)

        if bone_segments is not None and len(bone_segments):
            data = bone_segments[:MAX_BONES].astype("f4").tobytes()
            self.bones_vbo.write(data)
            self.ctx.disable(moderngl.DEPTH_TEST)
            self.line_prog["u_color"].value = (1.0, 0.6, 0.1)
            self.bones_vao.render(moderngl.LINES, vertices=len(data) // 12)
            self.ctx.enable(moderngl.DEPTH_TEST)
```

Points d'attention :
- Un squelette de plus de 128 joints est tronqué : ajouter à `model.infos` un message dans
  `MainWindow` si `len(skin.joints) > MAX_BONES` (les rigs Mixamo en ont ≤ 70).
- moderngl lève `KeyError` sur un uniform/attribut optimisé par le compilateur GLSL ;
  tous ceux déclarés ici sont utilisés.

Commit : `feat: moderngl renderer`.

---

## Tâche 11 — `ui/gl_view.py` et `main.py`

**Fichiers :** `viewer/ui/gl_view.py`, `viewer/main.py`

`viewer/ui/gl_view.py` :
```python
"""Vue OpenGL : boucle de rendu, souris, clavier."""
import moderngl
from PySide6.QtCore import QElapsedTimer, Qt, QTimer, Signal
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from viewer.camera import OrbitCamera
from viewer.player import Player
from viewer.renderer import Renderer


class GLView(QOpenGLWidget):
    time_changed = Signal(float)

    def __init__(self, player: Player, parent=None):
        super().__init__(parent)
        self.player = player
        self.camera = OrbitCamera()
        self.show_bones = False
        self.ctx = None
        self.renderer: Renderer | None = None
        self._skin_image = None
        self._last_pos = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    # --- état poussé par la fenêtre principale ---
    def model_changed(self) -> None:
        self._with_context(lambda: self.renderer.set_model(self.player.model))
        self.frame_all()

    def set_skin(self, image) -> None:
        self._skin_image = image
        self._with_context(lambda: self.renderer.set_skin(image))

    def frame_all(self) -> None:
        self.camera.frame(*self.player.bounds())
        self.update()

    def _with_context(self, fn) -> None:
        if self.renderer is None:
            return  # initializeGL appliquera l'état courant
        self.makeCurrent()
        try:
            fn()
        finally:
            self.doneCurrent()
        self.update()

    # --- OpenGL ---
    def initializeGL(self) -> None:
        self.ctx = moderngl.create_context()
        self.renderer = Renderer(self.ctx)
        self.renderer.set_model(self.player.model)
        self.renderer.set_skin(self._skin_image)

    def paintGL(self) -> None:
        fbo = self.ctx.detect_framebuffer(self.defaultFramebufferObject())
        ratio = self.devicePixelRatioF()
        w, h = max(int(self.width() * ratio), 1), max(int(self.height() * ratio), 1)
        fbo.viewport = (0, 0, w, h)
        view_proj = self.camera.projection(w / h) @ self.camera.view()
        frame = self.player.frame()
        segments = self.player.bone_segments(frame) if self.show_bones else None
        self.renderer.render(fbo, view_proj, frame, segments)

    def _tick(self) -> None:
        self.player.advance(self._clock.restart() / 1000.0)
        self.time_changed.emit(self.player.time)
        self.update()

    # --- souris / clavier ---
    def mousePressEvent(self, e):
        self._last_pos = e.position()

    def mouseMoveEvent(self, e):
        if self._last_pos is None:
            return
        d = e.position() - self._last_pos
        self._last_pos = e.position()
        if e.buttons() & Qt.MouseButton.LeftButton:
            self.camera.rotate(d.x(), d.y())
        elif e.buttons() & Qt.MouseButton.MiddleButton:
            self.camera.pan(d.x(), d.y(), self.height())
        self.update()

    def mouseReleaseEvent(self, e):
        self._last_pos = None

    def wheelEvent(self, e):
        self.camera.zoom(e.angleDelta().y() / 120)
        self.update()

    def mouseDoubleClickEvent(self, e):
        self.frame_all()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_F:
            self.frame_all()
        else:
            super().keyPressEvent(e)
```

`viewer/main.py` :
```python
import sys

from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication


def main() -> int:
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)  # avant la création de QApplication

    app = QApplication(sys.argv)
    from viewer.ui.main_window import MainWindow

    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

Vérification intermédiaire : remplacer temporairement `MainWindow` par une fenêtre ne
contenant que `GLView(player)` avec `player.set_model(load_glb(<un vrai perso>))` →
le perso s'affiche en T-pose sur la grille, rotation/zoom/pan/`F` fonctionnent.
Commit : `feat: OpenGL view widget`.

---

## Tâche 12 — `ui/main_window.py`

**Fichiers :** `viewer/ui/main_window.py`

```python
"""Fenêtre principale : sélection perso / skin / animation, lecture, vérification."""
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)

from viewer.gltf_loader import LoadedFile, LoadError, load_glb
from viewer.library import Library, scan
from viewer.mixamo import ValidationReport, validate
from viewer.player import Player
from viewer.renderer import MAX_BONES
from viewer.ui.gl_view import GLView

SPEEDS = [0.25, 0.5, 1.0, 1.5, 2.0]
TIMELINE_STEPS = 1000


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Characters Viewer")
        self.settings = QSettings("3D-Characters", "CharacterViewer")
        self.player = Player()
        self.library = Library()
        self.root: Path | None = None
        self._anim_cache: dict[Path, LoadedFile] = {}
        self._report: ValidationReport | None = None
        self._was_playing = True

        self.view = GLView(self.player)
        self.character_combo = QComboBox()
        self.skin_combo = QComboBox()
        self.anim_combo = QComboBox()
        self.play_button = QPushButton("⏸")
        self.speed_combo = QComboBox()
        self.speed_combo.addItems([f"{s}x" for s in SPEEDS])
        self.speed_combo.setCurrentIndex(SPEEDS.index(1.0))
        self.bones_check = QCheckBox("Afficher bones")
        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        self.details_button = QPushButton("détails…")
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, TIMELINE_STEPS)
        self.time_label = QLabel("0.00 / 0.00 s")

        self._build_layout()
        self._connect()

        root = self.settings.value("root")
        if root and Path(root).is_dir():
            self.open_root(Path(root), restore=True)

    # --- construction ---
    def _build_layout(self) -> None:
        open_action = self.menuBar().addAction("Dossier racine…")
        open_action.triggered.connect(self._choose_root)

        side = QVBoxLayout()
        for title, combo in (("Personnage", self.character_combo), ("Skin", self.skin_combo),
                             ("Animation", self.anim_combo)):
            side.addWidget(QLabel(title))
            side.addWidget(combo)
        playback = QHBoxLayout()
        playback.addWidget(self.play_button)
        playback.addWidget(QLabel("Vitesse"))
        playback.addWidget(self.speed_combo)
        side.addLayout(playback)
        side.addWidget(self.bones_check)
        side.addSpacing(12)
        side.addWidget(QLabel("Vérification"))
        side.addWidget(self.validation_label)
        side.addWidget(self.details_button)
        side.addStretch()
        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setFixedWidth(240)

        timeline = QHBoxLayout()
        timeline.addWidget(self.timeline)
        timeline.addWidget(self.time_label)
        right = QVBoxLayout()
        right.addWidget(self.view, 1)
        right.addLayout(timeline)

        main = QHBoxLayout()
        main.addWidget(side_widget)
        main.addLayout(right, 1)
        central = QWidget()
        central.setLayout(main)
        self.setCentralWidget(central)

    def _connect(self) -> None:
        self.character_combo.currentIndexChanged.connect(self._on_character)
        self.skin_combo.currentIndexChanged.connect(self._on_skin)
        self.anim_combo.currentIndexChanged.connect(self._on_animation)
        self.play_button.clicked.connect(self._toggle_play)
        self.speed_combo.currentIndexChanged.connect(lambda i: setattr(self.player, "speed", SPEEDS[i]))
        self.bones_check.toggled.connect(lambda on: setattr(self.view, "show_bones", on))
        self.details_button.clicked.connect(self._show_details)
        self.timeline.sliderPressed.connect(self._timeline_pressed)
        self.timeline.sliderMoved.connect(self._timeline_moved)
        self.timeline.sliderReleased.connect(self._timeline_released)
        self.view.time_changed.connect(self._on_time)

    # --- bibliothèque ---
    def _choose_root(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dossier racine", str(self.root or ""))
        if d:
            self.open_root(Path(d))

    def open_root(self, root: Path, restore: bool = False) -> None:
        self.root = root
        self.settings.setValue("root", str(root))
        self.library = scan(root)
        self._anim_cache.clear()
        for m in self.library.messages:
            self.statusBar().showMessage(m, 8000)

        self.anim_combo.blockSignals(True)
        self.anim_combo.clear()
        self.anim_combo.addItem("aucune (T-pose)")
        for a in self.library.animations:
            self.anim_combo.addItem(("⚠ " if a.error else "") + a.label)
        self.anim_combo.blockSignals(False)

        self.character_combo.blockSignals(True)
        self.character_combo.clear()
        self.character_combo.addItems([c.name for c in self.library.characters])
        self.character_combo.blockSignals(False)

        if restore:
            self._select_text(self.character_combo, self.settings.value("character"))
            self._select_text(self.anim_combo, self.settings.value("animation"))
        self._on_character(self.character_combo.currentIndex())
        self._on_animation(self.anim_combo.currentIndex())
        if restore:
            self._select_text(self.skin_combo, self.settings.value("skin"))
            self._on_skin(self.skin_combo.currentIndex())

    @staticmethod
    def _select_text(combo: QComboBox, text) -> None:
        if text:
            i = combo.findText(str(text))
            if i >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(i)
                combo.blockSignals(False)

    # --- sélection ---
    def _on_character(self, index: int) -> None:
        model = None
        self.skin_combo.blockSignals(True)
        self.skin_combo.clear()
        if 0 <= index < len(self.library.characters):
            entry = self.library.characters[index]
            try:
                model = load_glb(entry.model_path)
            except LoadError as e:
                self.statusBar().showMessage(str(e), 8000)
                self.character_combo.setItemText(index, f"⚠ {entry.name}")
            else:
                self.skin_combo.addItem("défaut")
                self.skin_combo.addItems([p.stem for p in entry.skins])
                self.settings.setValue("character", entry.name)
                for info in model.infos:
                    self.statusBar().showMessage(info, 8000)
                if any(len(s.joints) > MAX_BONES for s in model.skins):
                    self.statusBar().showMessage(f"Plus de {MAX_BONES} bones : squelette tronqué", 8000)
        self.skin_combo.blockSignals(False)
        self.player.set_model(model)
        self.view.set_skin(None)
        self.view.model_changed()
        self.anim_combo.setEnabled(model is not None and model.skinned)
        self._update_validation()

    def _on_skin(self, index: int) -> None:
        entry = self._current_character()
        if entry is None or index <= 0:
            self.view.set_skin(None)
            self.settings.setValue("skin", "défaut")
            return
        path = entry.skins[index - 1]
        try:
            image = Image.open(path).convert("RGBA")
        except Exception as e:
            self.statusBar().showMessage(f"Skin illisible : {path.name} ({e})", 8000)
            self.skin_combo.setCurrentIndex(0)
            return
        self.view.set_skin(image)
        self.settings.setValue("skin", path.stem)

    def _on_animation(self, index: int) -> None:
        clip = None
        if index > 0:
            entry = self.library.animations[index - 1]
            if entry.error:
                self.statusBar().showMessage(f"{entry.label} : {entry.error}", 8000)
            else:
                try:
                    if entry.path not in self._anim_cache:
                        self._anim_cache[entry.path] = load_glb(entry.path)
                    clip = self._anim_cache[entry.path].clips[entry.clip_index]
                except LoadError as e:
                    self.statusBar().showMessage(str(e), 8000)
        self.settings.setValue("animation", self.anim_combo.itemText(index))
        self.player.set_clip(clip)
        self._update_validation()

    def _current_character(self):
        i = self.character_combo.currentIndex()
        return self.library.characters[i] if 0 <= i < len(self.library.characters) else None

    # --- lecture ---
    def _toggle_play(self) -> None:
        self.player.playing = not self.player.playing
        self.play_button.setText("⏸" if self.player.playing else "▶")

    def _on_time(self, t: float) -> None:
        d = self.player.duration
        self.time_label.setText(f"{t:.2f} / {d:.2f} s")
        if not self.timeline.isSliderDown():
            self.timeline.blockSignals(True)
            self.timeline.setValue(int(t / d * TIMELINE_STEPS) if d > 0 else 0)
            self.timeline.blockSignals(False)

    def _timeline_pressed(self) -> None:
        self._was_playing = self.player.playing
        self.player.playing = False

    def _timeline_moved(self, value: int) -> None:
        self.player.seek(value / TIMELINE_STEPS * self.player.duration)

    def _timeline_released(self) -> None:
        self.player.playing = self._was_playing

    # --- vérification ---
    def _update_validation(self) -> None:
        model, clip = self.player.model, self.player.clip
        self._report = None
        if model is None:
            self.validation_label.setText("—")
        elif not model.skinned:
            self.validation_label.setText("Modèle statique (pas de squelette)")
        else:
            self._report = validate(model.joint_names(), clip.track_names() if clip else None)
            if self._report.ok:
                self.validation_label.setText("✅ Squelette Mixamo OK")
            else:
                self.validation_label.setText(f"⚠ {self._report.warnings} problème(s)")
        self.details_button.setEnabled(self._report is not None)

    def _show_details(self) -> None:
        if self._report is not None:
            QMessageBox.information(self, "Vérification Mixamo", self._report.details())
```

Commit : `feat: main window`.

---

## Tâche 13 — Vérification manuelle de bout en bout

Préparer une bibliothèque réelle, par exemple `C:\Dev\3D-Characters\sample\` (non versionnée,
ajouter `sample/` au `.gitignore`) : 1 personnage Mixamo exporté en GLB + 1 ou 2 PNG dans
`skins/`, et 2 à 3 animations Mixamo « without skin » converties en GLB.

Lancer : `.venv\Scripts\python -m viewer.main`, puis **Dossier racine…**.

Checklist :
- [ ] Le perso apparaît en T-pose, cadré, sur la grille.
- [ ] Clic gauche glissé → rotation ; molette → zoom ; clic milieu → pan ; double-clic / `F` → recadrage.
- [ ] Changement de skin → texture remplacée ; « défaut » → texture d'origine.
- [ ] Sélection d'une animation → elle joue en boucle, pieds au sol (pas de perso géant ni minuscule : ratio Hips).
- [ ] Pause/lecture, vitesses 0.25x et 2x.
- [ ] Glisser la timeline → scrub image par image, la lecture reprend au relâchement si elle était active.
- [ ] « Afficher bones » → squelette orange visible à travers le mesh.
- [ ] Panneau Vérification : ✅ sur un rig Mixamo complet ; renommer un bone dans un GLB de test → ⚠ et détail correct.
- [ ] Fichier `.glb` corrompu dans `Animations/` → entrée ⚠, aucun plantage.
- [ ] Fermer / relancer → dossier, perso, skin et animation restaurés.

Corriger les écarts, `pytest` vert, commit `chore: manual verification fixes` si nécessaire.
