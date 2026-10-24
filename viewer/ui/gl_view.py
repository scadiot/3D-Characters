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
        self._skin_images: dict[str, object] = {}
        self._last_pos = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    # --- état poussé par la fenêtre principale ---
    def model_changed(self) -> None:
        self._skin_images = {}
        self._with_context(lambda: (self.renderer.clear_skins(), self.renderer.set_model(self.player.model)))
        self.frame_all()

    def set_skin(self, material: str, image) -> None:
        """Remplace la texture base color d'un matériau (None : texture d'origine)."""
        if image is None:
            self._skin_images.pop(material, None)
        else:
            self._skin_images[material] = image
        self._with_context(lambda: self.renderer.set_skin(material, image))

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
        for material, image in self._skin_images.items():
            self.renderer.set_skin(material, image)

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
