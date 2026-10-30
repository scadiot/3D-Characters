"""Rendu moderngl : mesh skinné (standard ou cel shading avec contour), grille au sol, bones en lignes."""
import moderngl
import numpy as np
from PIL import Image

from viewer.gltf_loader import LoadedFile
from viewer.player import FrameData
from viewer.render_settings import RenderSettings, camera_eye, smooth_normals

MAX_BONES = 128
BACKGROUND = (0.18, 0.19, 0.21, 1.0)

MESH_VS = """
#version 330
layout(std140) uniform Bones { mat4 u_bones[128]; };
uniform mat4 u_view_proj;
uniform mat4 u_model;
uniform int u_skinned;
uniform float u_outline;  // passe contour : épaisseur en pixels, sinon 0
uniform vec2 u_viewport;
in vec3 in_position;
in vec3 in_normal;
in vec3 in_smooth_normal;
in vec2 in_uv;
in ivec4 in_joints;
in vec4 in_weights;
out vec3 v_normal;
out vec3 v_world;
out vec2 v_uv;
void main() {
    mat4 m = u_model;
    if (u_skinned == 1) {
        m = in_weights.x * u_bones[in_joints.x] + in_weights.y * u_bones[in_joints.y]
          + in_weights.z * u_bones[in_joints.z] + in_weights.w * u_bones[in_joints.w];
    }
    vec4 world = m * vec4(in_position, 1.0);
    v_normal = mat3(m) * in_normal;
    v_world = world.xyz;
    v_uv = in_uv;
    vec4 clip = u_view_proj * world;
    if (u_outline > 0.0) {
        // Coque inversée : extrusion le long de la normale, d'une épaisseur constante à l'écran.
        vec2 dir = (u_view_proj * vec4(mat3(m) * in_smooth_normal, 0.0)).xy;
        if (length(dir) > 1e-6) {
            clip.xy += normalize(dir) * u_outline * 2.0 / u_viewport * clip.w;
        }
    }
    gl_Position = clip;
}
"""

MESH_FS = """
#version 330
uniform sampler2D u_tex;
uniform vec4 u_base_color;
uniform vec3 u_light_dir;
uniform int u_mode;  // 0 : standard, 1 : cel shading, 2 : contour
uniform float u_shadow;
uniform float u_bands;
uniform float u_softness;
uniform float u_rim;
uniform float u_rim_width;
uniform vec4 u_eye;  // position de la caméra (w = 1) ou direction vers elle (w = 0)
uniform vec3 u_outline_color;
in vec3 v_normal;
in vec3 v_world;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec4 albedo = texture(u_tex, v_uv) * u_base_color;
    if (u_mode == 2) {
        f_color = vec4(u_outline_color, albedo.a);
        return;
    }
    vec3 n = normalize(gl_FrontFacing ? v_normal : -v_normal);
    float ndl = dot(n, -u_light_dir);
    if (u_mode == 0) {
        f_color = vec4(albedo.rgb * (u_shadow + (1.0 - u_shadow) * max(ndl, 0.0)), albedo.a);
        return;
    }
    // Tons en aplats : lambert enveloppé découpé en u_bands niveaux, transitions anticrénelées.
    float level = (ndl * 0.5 + 0.5) * u_bands;
    float aa = clamp(max(u_softness, fwidth(level)), 1e-4, 1.0);
    float band = floor(level) + smoothstep(1.0 - aa, 1.0, fract(level));
    float lit = clamp(band, 0.0, u_bands - 1.0) / (u_bands - 1.0);
    vec3 color = albedo.rgb * (u_shadow + (1.0 - u_shadow) * lit);
    // Liseré sur les bords tournés à l'opposé de la caméra.
    vec3 v = normalize(u_eye.xyz - v_world * u_eye.w);
    float fresnel = 1.0 - max(dot(n, v), 0.0);
    float edge = 1.0 - u_rim_width;
    float w = fwidth(fresnel);
    float rim = u_rim_width > 0.0 ? smoothstep(edge - w, edge + w, fresnel) : 0.0;
    f_color = vec4(mix(color, vec3(1.0), rim * u_rim), albedo.a);
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
    def __init__(self, vao, buffers, texture, base_color, skin, node, material):
        self.vao, self.buffers, self.texture = vao, buffers, texture
        self.base_color, self.skin, self.node, self.material = base_color, skin, node, material

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
        self.skin_textures: dict[str, moderngl.Texture] = {}  # matériau -> skin choisie
        self.settings = RenderSettings()
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
                self.ctx.buffer(smooth_normals(m.positions, m.normals).astype("f4").tobytes()),
            ]
            index = self.ctx.buffer(m.indices.astype("u4").tobytes())
            vao = self.ctx.vertex_array(self.mesh_prog, [
                (buffers[0], "3f", "in_position"),
                (buffers[1], "3f", "in_normal"),
                (buffers[2], "2f", "in_uv"),
                (buffers[3], "4i", "in_joints"),
                (buffers[4], "4f", "in_weights"),
                (buffers[5], "3f", "in_smooth_normal"),
            ], index_buffer=index, index_element_size=4)
            texture = self._texture(m.texture) if m.texture is not None else None
            self.meshes.append(_GpuMesh(vao, buffers + [index], texture,
                                        tuple(float(x) for x in m.base_color), m.skin, m.node, m.material))

    def set_skin(self, material: str, image: Image.Image | None) -> None:
        old = self.skin_textures.pop(material, None)
        if old:
            old.release()
        if image is not None:
            self.skin_textures[material] = self._texture(image)

    def clear_skins(self) -> None:
        for tex in self.skin_textures.values():
            tex.release()
        self.skin_textures = {}

    def render(self, fbo, view_proj: np.ndarray, frame: FrameData | None, bone_segments: np.ndarray | None,
               background: tuple[float, float, float, float] = BACKGROUND, grid: bool = True,
               pixel_scale: float = 1.0) -> None:
        """`pixel_scale` : pixels du framebuffer par pixel de l'image finale (épaisseur du contour)."""
        fbo.use()
        fbo.clear(*background, depth=1.0)
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.disable(moderngl.CULL_FACE)
        vp = _gl_mat(view_proj)

        self.line_prog["u_view_proj"].write(vp)
        if grid:
            self.line_prog["u_color"].value = (0.32, 0.33, 0.36)
            self.grid_vao.render(moderngl.LINES)

        if frame is not None:
            s = self.settings
            prog = self.mesh_prog
            prog["u_view_proj"].write(vp)
            prog["u_light_dir"].value = s.light_dir()
            prog["u_tex"].value = 0
            prog["u_shadow"].value = s.shadow
            prog["u_bands"].value = float(s.bands)
            prog["u_softness"].value = s.softness
            prog["u_rim"].value = s.rim
            prog["u_rim_width"].value = s.rim_width
            prog["u_eye"].value = tuple(camera_eye(view_proj))
            prog["u_outline_color"].value = s.outline_color
            prog["u_viewport"].value = tuple(float(x) for x in fbo.viewport[2:])
            mode = 1 if s.shading == "cel" else 0
            outline = s.outline_width * pixel_scale if s.outline else 0.0
            self.bones_ubo.bind_to_uniform_block(0)
            for m in self.meshes:
                if m.skin is not None:
                    self.bones_ubo.write(_gl_mats(frame.joint_matrices[m.skin][:MAX_BONES]))
                    prog["u_skinned"].value = 1
                    prog["u_model"].write(_gl_mat(np.eye(4)))
                else:
                    prog["u_skinned"].value = 0
                    prog["u_model"].write(_gl_mat(frame.globals[m.node]))
                (self.skin_textures.get(m.material) or m.texture or self.white).use(0)
                prog["u_base_color"].value = m.base_color
                prog["u_mode"].value, prog["u_outline"].value = mode, 0.0
                m.vao.render(moderngl.TRIANGLES)
                if outline > 0:
                    prog["u_mode"].value, prog["u_outline"].value = 2, outline
                    self.ctx.enable(moderngl.CULL_FACE)
                    self.ctx.cull_face = "front"
                    m.vao.render(moderngl.TRIANGLES)
                    self.ctx.cull_face = "back"
                    self.ctx.disable(moderngl.CULL_FACE)

        if bone_segments is not None and len(bone_segments):
            data = bone_segments[:MAX_BONES].astype("f4").tobytes()
            self.bones_vbo.write(data)
            self.ctx.disable(moderngl.DEPTH_TEST)
            self.line_prog["u_color"].value = (1.0, 0.6, 0.1)
            self.bones_vao.render(moderngl.LINES, vertices=len(data) // 12)
            self.ctx.enable(moderngl.DEPTH_TEST)
