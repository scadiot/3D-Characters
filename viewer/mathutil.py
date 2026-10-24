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


def orthographic(left: float, right: float, bottom: float, top: float, near: float, far: float) -> np.ndarray:
    m = np.eye(4)
    m[0, 0] = 2 / (right - left)
    m[1, 1] = 2 / (top - bottom)
    m[2, 2] = -2 / (far - near)
    m[0, 3] = -(right + left) / (right - left)
    m[1, 3] = -(top + bottom) / (top - bottom)
    m[2, 3] = -(far + near) / (far - near)
    return m
