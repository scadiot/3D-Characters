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
