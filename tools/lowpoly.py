"""Briques communes aux générateurs de personnages low poly sur squelette Mixamo.

Convention : T-pose, le personnage regarde vers +Z, côté gauche en +X, unités en mètres.
Les os n'ont pas de rotation ; seules leurs positions monde définissent le squelette.
Ombrage plat : chaque triangle a ses propres sommets.

Une influence (`Influence`) est soit un nom de bone (poids 1), soit un dict {bone: poids}.

UV : chaque primitive déplie ses triangles dans une île (`Part.chart`) en mètres, sans étirement notable ;
`Part.pack` range ensuite toutes les îles dans un atlas, à densité de texels constante, et
`Part.paint` peint chaque triangle de la couleur de son groupe.
"""
import io
from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image, ImageDraw
from pygltflib import (
    GLTF2, Accessor, Asset, Attributes, Buffer, BufferView, Material, Mesh, Node,
    PbrMetallicRoughness, Primitive, Sampler, Scene, Skin, Texture, TextureInfo,
)
from pygltflib import Image as GltfImage

FLOAT, UBYTE, USHORT = 5126, 5121, 5123
NEAREST = 9728
PREFIX = "mixamorig:"

Influence = Union[str, dict]


class Rig:
    def __init__(self, bones: list):
        """bones : liste de (nom, parent, position monde), parents avant enfants."""
        self.bones = bones
        self.index = {name: i for i, (name, _, _) in enumerate(bones)}
        self.world = {name: np.array(p, float) for name, _, p in bones}

    def warped(self, warp) -> "Rig":
        """Même squelette, positions passées par `warp` (voir `Part`)."""
        return Rig([(name, parent, warp(np.array(pos, float))) for name, parent, pos in self.bones])


class Part:
    """Triangles regroupés par couleur ; chaque sommet porte ses influences et un UV.

    Une entrée de groupe est [positions (3, 3), poids par sommet, uvs (3, 2), île].
    textured : groupes supplémentaires dont les UV sont déjà définitifs (île None)
    et qui reçoivent chacun leur propre texture à l'export (voir `export`).
    warp : déformation appliquée aux positions des triangles (pas aux UV) ; `rig` doit alors être
    le squelette déformé par la même fonction (`Rig.warped`). Sert à changer les proportions d'un modèle.
    """

    def __init__(self, rig: Rig, colors: dict, textured: tuple = (), warp=None):
        self.rig = rig
        self.warp = warp
        self.colors = colors
        self.textured = set(textured)
        self.groups: dict[str, list] = {c: [] for c in (*colors, *textured)}
        self.charts = 0
        self.atlas_size: int | None = None

    def chart(self) -> int:
        """Nouvelle île d'UV."""
        self.charts += 1
        return self.charts - 1

    def _weights(self, influence: Influence) -> dict:
        if isinstance(influence, str):
            influence = {influence: 1.0}
        return {self.rig.index[b]: w for b, w in influence.items()}

    def tri(self, color: str, influence: Influence, a, b, c, influences=None, uvs=None, chart=None) -> None:
        """influences : une influence par sommet ; sinon `influence` pour les trois.
        uvs : trois UV, en mètres dans l'île `chart`, ou définitifs pour un groupe texturé."""
        per_vertex = influences or (influence, influence, influence)
        points = np.array([a, b, c], float)
        if self.warp is not None:
            points = np.array([self.warp(q) for q in points])
        self.groups[color].append([points, [self._weights(i) for i in per_vertex],
                                   None if uvs is None else np.array(uvs, float), chart])

    def quad(self, color, influence, a, b, c, d, influences=None, uvs=None, chart=None) -> None:
        ia, ib, ic, id_ = influences or (influence,) * 4
        ua, ub, uc, ud = uvs if uvs is not None else (None,) * 4
        self.tri(color, influence, a, b, c, (ia, ib, ic), None if uvs is None else (ua, ub, uc), chart)
        self.tri(color, influence, a, c, d, (ia, ic, id_), None if uvs is None else (ua, uc, ud), chart)

    def _atlas_entries(self):
        return [e for group, entries in self.groups.items() if group not in self.textured for e in entries]

    def pack(self, size: int = 1024, padding: int = 4) -> float:
        """Range les îles dans [0, 1]² à échelle commune maximale ; renvoie les pixels par mètre."""
        charts: dict[int, list] = {}
        for e in self._atlas_entries():
            if e[3] is None:
                raise ValueError("triangle sans île d'UV")
            charts.setdefault(e[3], []).append(e)
        islands = []
        for entries in charts.values():
            pts = np.concatenate([e[2] for e in entries])
            lo, hi = pts.min(axis=0), pts.max(axis=0)
            rotate = (hi - lo)[1] > (hi - lo)[0]  # îles couchées : meilleur rangement par étagères
            islands.append((entries, lo, hi, rotate))
        dims = [((hi - lo)[::-1] if rot else hi - lo) for _, lo, hi, rot in islands]
        order = sorted(range(len(islands)), key=lambda k: -dims[k][1])
        pad = padding / size

        def place(scale: float):
            spots, x, y, shelf = {}, pad, pad, 0.0
            for k in order:
                w, h = dims[k] * scale
                if x + w + pad > 1:
                    x, y, shelf = pad, y + shelf + 2 * pad, 0.0
                spots[k] = (x, y)
                x, shelf = x + w + 2 * pad, max(shelf, h)
            return spots if y + shelf + pad <= 1 else None

        low, high = 0.0, 100.0
        for _ in range(40):
            mid = (low + high) / 2
            low, high = (mid, high) if place(mid) else (low, mid)
        spots = place(low)
        for k, (entries, lo, hi, rotate) in enumerate(islands):
            for e in entries:
                local = e[2] - lo
                if rotate:
                    local = np.stack([local[:, 1], (hi - lo)[0] - local[:, 0]], axis=1)
                e[2] = np.asarray(spots[k]) + local * low
        self.atlas_size = size
        return low * size

    def paint(self, colors: dict | None = None, size: int | None = None) -> Image.Image:
        """Texture de l'atlas : chaque triangle aux couleurs de son groupe, puis le fond rempli en
        prolongeant les îles, pour que les mipmaps (faces vues de biais) ne ramènent jamais le fond."""
        colors = colors or self.colors
        size = size or self.atlas_size
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        for group, entries in self.groups.items():
            if group not in self.textured:
                for e in entries:
                    xy = [tuple(q * size) for q in e[2]]
                    draw.polygon(xy, fill=_rgb255(colors[group]), outline=_rgb255(colors[group]))
        return dilate(image)

    def layout(self, size: int | None = None) -> Image.Image:
        """Gabarit pour peindre l'atlas : la texture par défaut et les arêtes des triangles."""
        image = self.paint(size=size)
        draw = ImageDraw.Draw(image)
        for e in self._atlas_entries():
            draw.polygon([tuple(q * image.size[0]) for q in e[2]], outline=(20, 20, 20, 255))
        return image


def dilate(image: Image.Image) -> Image.Image:
    """Remplit les pixels transparents avec la couleur des pixels opaques voisins, jusqu'à tout couvrir."""
    rgba = np.asarray(image, np.float32)
    filled = rgba[..., 3] > 0
    if not filled.any():
        return image
    color = _push_pull(rgba[..., :3], filled)
    return Image.fromarray(np.dstack([color, np.full(filled.shape, 255.0)]).round().astype(np.uint8), "RGBA")


def _push_pull(color: np.ndarray, filled: np.ndarray) -> np.ndarray:
    """Pyramide : chaque niveau moyenne les pixels remplis du précédent, puis les trous reçoivent
    la couleur du niveau plus grossier. Coût linéaire, quelle que soit la taille des trous."""
    if filled.all() or min(filled.shape) == 1:
        return np.where(filled[..., None], color, color[filled].mean(axis=0))
    h, w = filled.shape
    ph, pw = h % 2, w % 2
    c = np.pad(color * filled[..., None], ((0, ph), (0, pw), (0, 0)))
    m = np.pad(filled.astype(np.float32), ((0, ph), (0, pw)))
    c2 = c.reshape(c.shape[0] // 2, 2, c.shape[1] // 2, 2, 3).sum(axis=(1, 3))
    m2 = m.reshape(m.shape[0] // 2, 2, m.shape[1] // 2, 2).sum(axis=(1, 3))
    coarse = _push_pull(c2 / np.maximum(m2, 1)[..., None], m2 > 0)
    up = coarse.repeat(2, axis=0).repeat(2, axis=1)[:h, :w]
    return np.where(filled[..., None], color, up)


def _rgb255(color) -> tuple:
    return tuple(round(c * 255) for c in color[:3]) + (255,)


def frame(axis) -> tuple[np.ndarray, np.ndarray]:
    """Deux vecteurs unitaires u, v tels que (u, v, axis) soit direct."""
    axis = np.asarray(axis, float)
    axis = axis / np.linalg.norm(axis)
    helper = np.array([0, 0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0, 0])
    u = np.cross(axis, helper)
    u /= np.linalg.norm(u)
    return u, np.cross(axis, u)


def grid_uvs(rings: list) -> list:
    """Déroule une bande d'anneaux fermés (même nombre de points, dans l'ordre) coupée entre le dernier
    et le premier point : u = longueur le long de l'anneau (centrée), v = longueur le long des colonnes.
    Renvoie uv[k][i] pour i = 0..n (la colonne n double la colonne 0, de l'autre côté de la couture)."""
    n = len(rings[0])
    closed = [list(r) + [r[0]] for r in rings]
    result, v = [], np.zeros(n + 1)
    for k, ring in enumerate(closed):
        if k:
            v = v + np.linalg.norm(np.array(ring) - np.array(closed[k - 1]), axis=1)
        u = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(np.array(ring), axis=0), axis=1))])
        result.append([np.array([ui - u[-1] / 2, vi]) for ui, vi in zip(u, v)])
    return result


def planar_uvs(points, origin, e1, e2) -> list:
    return [np.array([np.dot(q - origin, e1), np.dot(q - origin, e2)]) for q in points]


def loft(p: Part, colors, axis, rings: list, sides=8, caps=(True, True), seam=None) -> None:
    """Relie des anneaux successifs le long de `axis`.

    rings : (centre, (ru, rv), influence) ; ru et rv sont les rayons selon les vecteurs de `frame(axis)`.
    L'influence peut être une fonction position -> influence, évaluée pour chaque sommet de l'anneau.
    colors : une couleur, ou une par segment (len(rings) - 1).
    seam : direction où couper la bande pour la déplier (côté peu visible) ; bouchons dépliés à plat.
    """
    if isinstance(colors, str):
        colors = [colors] * (len(rings) - 1)
    u, v = frame(axis)
    angles = np.arange(sides) * 2 * np.pi / sides + np.pi / sides
    if seam is not None:
        # la couture passe entre le dernier et le premier sommet : on commence juste après `seam`
        mids = angles - np.pi / sides
        start = int(np.argmax([np.dot(np.cos(t) * u + np.sin(t) * v, seam) for t in mids]))
        angles = np.roll(angles, -start)
    pts = [[np.asarray(c, float) + r[0] * np.cos(t) * u + r[1] * np.sin(t) * v for t in angles]
           for c, r, _ in rings]
    infl = [[i(q) if callable(i) else i for q in ring] for ring, (_, _, i) in zip(pts, rings)]
    uv, chart = grid_uvs(pts), p.chart()
    for k in range(len(rings) - 1):
        a, b, ia, ib = pts[k], pts[k + 1], infl[k], infl[k + 1]
        for i in range(sides):
            j = (i + 1) % sides
            p.quad(colors[k], ia[i], a[i], a[j], b[j], b[i], (ia[i], ia[j], ib[j], ib[i]),
                   (uv[k][i], uv[k][i + 1], uv[k + 1][i + 1], uv[k + 1][i]), chart)
    for end, color, ring, ia, order in ((caps[0], colors[0], pts[0], infl[0], -1), (caps[1], colors[-1], pts[-1], infl[-1], 1)):
        if not end:
            continue
        cap, flat = p.chart(), planar_uvs(ring, ring[0], u, order * v)
        for i in range(1, sides - 1):
            i1, i2 = (i, i + 1) if order > 0 else (i + 1, i)
            p.tri(color, ia[0], ring[0], ring[i1], ring[i2], (ia[0], ia[i1], ia[i2]),
                  (flat[0], flat[i1], flat[i2]), cap)


def prism(p: Part, color, influence, a, b, ra, rb, sides=6, seam=None) -> None:
    """Tronc de prisme fermé de a vers b, rayons ra puis rb."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    loft(p, color, b - a, [(a, (ra, ra), influence), (b, (rb, rb), influence)], sides, seam=seam)


def _planar_quad(p: Part, color, influence, a, b, c, d) -> None:
    """Quad plan déplié dans sa propre île."""
    e1 = (b - a) / np.linalg.norm(b - a)
    n = np.cross(b - a, d - a)
    e2 = np.cross(n / np.linalg.norm(n), e1)
    p.quad(color, influence, a, b, c, d, uvs=planar_uvs((a, b, c, d), a, e1, e2), chart=p.chart())


def box(p: Part, color, influence, center, size, taper=(1.0, 1.0)) -> None:
    """Boîte centrée ; taper réduit la face supérieure (+Y) en X et Z. Une île par face."""
    c, h = np.asarray(center, float), np.asarray(size, float) / 2
    corners = ((-1, -1), (1, -1), (1, 1), (-1, 1))
    bottom = [c + (sx * h[0], -h[1], sz * h[2]) for sx, sz in corners]
    top = [c + (sx * h[0] * taper[0], h[1], sz * h[2] * taper[1]) for sx, sz in corners]
    _planar_quad(p, color, influence, *bottom)
    _planar_quad(p, color, influence, *reversed(top))
    for i in range(4):
        j = (i + 1) % 4
        _planar_quad(p, color, influence, bottom[i], top[i], top[j], bottom[j])


def ball(p: Part, color, influence, center, r, scale=(1.0, 1.0, 1.0), detail=0) -> None:
    """Icosaèdre, éventuellement aplati par `scale` ; chaque niveau de `detail` quadruple les faces.
    Dépliage : deux hémisphères projetés à plat le long de l'axe le plus aplati."""
    t = (1 + 5 ** 0.5) / 2
    verts = np.array([(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t),
                      (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)], float)
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4),
             (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8),
             (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    tris = [verts[list(f)] / np.linalg.norm(verts[0]) for f in faces]
    for _ in range(detail):
        finer = []
        for a, b, c in tris:
            ab, bc, ca = (m / np.linalg.norm(m) for m in (a + b, b + c, c + a))
            finer += [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]
        tris = finer
    scale = np.asarray(scale, float)
    flat = int(np.argmin(scale))
    e1, e2 = (k for k in range(3) if k != flat)
    halves = {-1: p.chart(), 1: p.chart()}
    for tri in tris:
        local = [np.asarray(v) * r * scale for v in tri]
        side = 1 if sum(q[flat] for q in local) >= 0 else -1
        p.tri(color, influence, *(q + center for q in local),
              uvs=[(side * q[e1], q[e2]) for q in local], chart=halves[side])


class _Builder:
    def __init__(self, generator: str):
        self.gltf = GLTF2(asset=Asset(version="2.0", generator=generator), scene=0)
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
            kw = {"min": arr.min(axis=0).tolist(), "max": arr.max(axis=0).tolist()}
        self.gltf.accessors.append(Accessor(bufferView=self.view(arr.tobytes()), componentType=component,
                                            count=len(arr), type=gl_type, **kw))
        return len(self.gltf.accessors) - 1

    def save(self, path: Path) -> None:
        self.gltf.buffers = [Buffer(byteLength=len(self.data))]
        self.gltf.set_binary_blob(bytes(self.data))
        self.gltf.save_binary(str(path))


def _skin_attributes(influences: list) -> tuple[np.ndarray, np.ndarray]:
    joints = np.zeros((len(influences), 4), np.uint8)
    weights = np.zeros((len(influences), 4), np.float32)
    for k, infl in enumerate(influences):
        top = sorted(infl.items(), key=lambda item: -item[1])[:4]
        total = sum(w for _, w in top)
        for slot, (bone, w) in enumerate(top):
            joints[k, slot] = bone
            weights[k, slot] = w / total
    return joints, weights


def export(path: Path, part: Part, name: str, generator: str, atlas: Image.Image | None = None,
           textures: dict | None = None) -> int:
    """Écrit le GLB et renvoie le nombre de triangles.

    atlas : texture du matériau « body » partagé par tous les groupes non texturés, avec les UV de
    `Part.pack` ; sinon un matériau uni par couleur, sans UV.
    textures : {groupe texturé: image} ; chaque groupe devient un matériau du même nom, avec ses UV.
    """
    textures = textures or {}
    rig = part.rig
    b = _Builder(generator)
    g = b.gltf
    for bone, parent, _ in rig.bones:
        local = rig.world[bone] - (rig.world[parent] if parent else 0)
        g.nodes.append(Node(name=PREFIX + bone, translation=local.tolist()))
    for bone, parent, _ in rig.bones:
        if parent:
            g.nodes[rig.index[parent]].children.append(rig.index[bone])
    root = rig.bones[0][0]
    g.nodes.append(Node(name=name, mesh=0, skin=0))
    g.scenes = [Scene(nodes=[rig.index[root], len(rig.bones)])]

    # Os sans rotation : la matrice de bind inverse est une simple translation (column-major).
    inverse_bind = np.tile(np.eye(4, dtype=np.float32), (len(rig.bones), 1, 1))
    for bone, i in rig.index.items():
        inverse_bind[i, 3, :3] = -rig.world[bone]
    g.skins = [Skin(name="Armature", skeleton=rig.index[root], joints=list(range(len(rig.bones))),
                    inverseBindMatrices=b.accessor(inverse_bind.reshape(-1, 16), "MAT4", FLOAT))]

    def textured_material(material_name: str, image: Image.Image) -> int:
        png = io.BytesIO()
        image.save(png, format="PNG")
        g.images.append(GltfImage(name=material_name, bufferView=b.view(png.getvalue()), mimeType="image/png"))
        g.textures.append(Texture(source=len(g.images) - 1))
        g.materials.append(Material(name=material_name, pbrMetallicRoughness=PbrMetallicRoughness(
            baseColorTexture=TextureInfo(index=len(g.textures) - 1), metallicFactor=0.0, roughnessFactor=0.7)))
        return len(g.materials) - 1

    if atlas is not None and part.atlas_size is None:
        raise ValueError("appeler Part.pack avant d'exporter un atlas")
    body = textured_material("body", atlas) if atlas is not None else None
    own = {group: textured_material(group, image) for group, image in textures.items() if part.groups[group]}

    primitives, triangles = [], 0
    for color, tris in part.groups.items():
        if not tris:
            continue
        if color in own:
            material = own[color]
        elif body is not None:
            material = body
        else:
            g.materials.append(Material(name=color, pbrMetallicRoughness=PbrMetallicRoughness(
                baseColorFactor=list(part.colors[color]), metallicFactor=0.0, roughnessFactor=0.7)))
            material = len(g.materials) - 1
        pos = np.concatenate([e[0] for e in tris]).astype(np.float32)
        normals = np.repeat([np.cross(t[1] - t[0], t[2] - t[0]) for t, *_ in tris], 3, axis=0)
        normals = (normals / np.linalg.norm(normals, axis=1, keepdims=True)).astype(np.float32)
        joints, weights = _skin_attributes([w for e in tris for w in e[1]])
        attributes = Attributes(
            POSITION=b.accessor(pos, "VEC3", FLOAT, minmax=True),
            NORMAL=b.accessor(normals, "VEC3", FLOAT),
            JOINTS_0=b.accessor(joints, "VEC4", UBYTE),
            WEIGHTS_0=b.accessor(weights, "VEC4", FLOAT),
        )
        if color in own or body is not None:
            uvs = np.concatenate([e[2] for e in tris]).astype(np.float32)
            attributes.TEXCOORD_0 = b.accessor(uvs, "VEC2", FLOAT)
        indices = np.arange(len(pos), dtype=np.uint16)
        primitives.append(Primitive(attributes=attributes, indices=b.accessor(indices, "SCALAR", USHORT),
                                    material=material))
        triangles += len(tris)
    g.meshes = [Mesh(name=name, primitives=primitives)]
    path.parent.mkdir(parents=True, exist_ok=True)
    b.save(path)
    return triangles
