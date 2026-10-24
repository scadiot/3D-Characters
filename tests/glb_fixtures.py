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
