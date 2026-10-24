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


def test_bounds_use_skinned_rest_positions(model_path):
    # Mesh stocké en cm : positions ×100, compensées dans l'inverse bind.
    f = load_glb(model_path)
    f.meshes[0].positions = f.meshes[0].positions * 100
    f.skins[0].inverse_bind = f.skins[0].inverse_bind @ np.diag([0.01, 0.01, 0.01, 1])
    p = Player()
    p.set_model(f)
    lo, hi = p.bounds()
    assert np.allclose(lo, [-0.1, 1, 0], atol=1e-6) and np.allclose(hi, [0.1, 1.2, 0], atol=1e-6)


def test_model_facing_minus_z_is_turned_toward_camera():
    from pathlib import Path
    from test_skeleton import _legs
    from viewer.gltf_loader import LoadedFile
    p = Player()
    p.set_model(LoadedFile(Path("x.glb"), _legs(np.pi), [], [], []))
    g = p.frame().globals
    assert g[2][0, 3] > 0 and g[3][0, 3] < 0  # jambe gauche du côté +X, comme un perso regardant +Z


def test_skinned_points_match_rest_vertices(model_path):
    from viewer.player import skinned_points
    p = Player()
    p.set_model(load_glb(model_path))
    pts = skinned_points(p.model, p.frame())
    assert pts.shape == (4, 3)
    assert np.allclose(pts, p.model.meshes[0].positions, atol=1e-6)
