"""Rendu hors écran d'une pose dans une image RGBA à fond transparent."""
import moderngl
import numpy as np
from PIL import Image

from viewer.player import FrameData
from viewer.renderer import Renderer


class SpriteRenderer:
    """Réutilise le `Renderer` de la vue (mêmes meshes et skins) sur un framebuffer dédié.

    Doit être utilisé avec le contexte OpenGL de la vue courant.
    """

    def __init__(self, ctx: moderngl.Context, renderer: Renderer):
        self.ctx, self.renderer = ctx, renderer
        self._size: tuple[int, int] | None = None
        self._fbo = None
        self._attachments = []

    def _framebuffer(self, size: tuple[int, int]):
        if size != self._size:
            self.release()
            color = self.ctx.texture(size, 4)
            depth = self.ctx.depth_renderbuffer(size)
            self._fbo = self.ctx.framebuffer([color], depth)
            self._attachments, self._size = [color, depth], size
        return self._fbo

    def render(self, frame: FrameData, view_proj: np.ndarray, size: tuple[int, int],
               pixel_scale: float = 1.0) -> Image.Image:
        fbo = self._framebuffer(size)
        fbo.viewport = (0, 0, *size)
        self.renderer.render(fbo, view_proj, frame, None, background=(0.0, 0.0, 0.0, 0.0), grid=False,
                             pixel_scale=pixel_scale)
        data = fbo.read(components=4, alignment=1)
        return Image.frombytes("RGBA", size, data).transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    def release(self) -> None:
        if self._fbo is not None:
            self._fbo.release()
            for a in self._attachments:
                a.release()
        self._fbo, self._attachments, self._size = None, [], None
