import numpy as np

from viewer.camera import OrbitCamera
from viewer.mathutil import orthographic
from viewer.render_settings import RenderSettings, camera_eye, smooth_normals


def test_round_trip():
    s = RenderSettings(shading="standard", bands=5, softness=0.2, outline=False, outline_color=(1.0, 0.5, 0.0))
    assert RenderSettings.from_dict(s.to_dict()) == s


def test_invalid_values_fall_back_or_are_clamped():
    s = RenderSettings.from_dict({"shading": "plasma", "bands": 99, "softness": "x", "shadow": -1,
                                  "outline_width": float("nan"), "outline_color": [2, "a"], "light_elevation": 500})
    d = RenderSettings()
    assert (s.shading, s.bands, s.softness, s.shadow) == (d.shading, 8, d.softness, 0.0)
    assert (s.outline_width, s.outline_color, s.light_elevation) == (d.outline_width, d.outline_color, 90)
    assert RenderSettings.from_dict(None) == d


def test_light_dir_points_down_from_azimuth():
    s = RenderSettings(light_azimuth=0, light_elevation=90)
    assert np.allclose(s.light_dir(), [0, -1, 0])
    s = RenderSettings(light_azimuth=90, light_elevation=0)
    assert np.allclose(s.light_dir(), [-1, 0, 0])  # lumière venant de +X


def test_camera_eye_perspective():
    c = OrbitCamera()
    vp = c.projection(1.5) @ c.view()
    eye = camera_eye(vp)
    assert eye[3] == 1.0 and np.allclose(eye[:3], c.eye())


def test_camera_eye_orthographic_is_direction_towards_camera():
    eye = camera_eye(orthographic(-1, 1, -1, 1, -5, 5))
    assert np.allclose(eye, [0, 0, 1, 0])


def test_smooth_normals_average_coincident_vertices():
    positions = np.array([[0, 0, 0], [0, 0, 0], [1, 0, 0]], dtype="f4")
    normals = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype="f4")
    out = smooth_normals(positions, normals)
    assert np.allclose(out[0], out[1]) and np.allclose(out[0], [np.sqrt(0.5), np.sqrt(0.5), 0])
    assert np.allclose(out[2], [0, 0, 1])
    assert len(smooth_normals(np.zeros((0, 3)), np.zeros((0, 3)))) == 0
