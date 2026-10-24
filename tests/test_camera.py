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
