import numpy as np
import pytest

from viewer import mathutil as mu
from viewer.animation import Track, apply_clip, hips_ratio, loop_time, sample_track
from viewer.gltf_loader import load_glb

LIN = Track(np.array([0.0, 1.0]), np.array([[0, 1, 0], [0, 2, 0.0]]), "LINEAR")


@pytest.mark.parametrize("t,expected", [(0, 1), (0.5, 1.5), (1, 2), (-1, 1), (5, 2)])
def test_linear_translation(t, expected):
    assert np.allclose(sample_track(LIN, t), [0, expected, 0])


def test_step():
    tr = Track(np.array([0.0, 0.5]), np.array([[0, 0, 0.0], [1, 1, 1.0]]), "STEP")
    assert np.allclose(sample_track(tr, 0.49), [0, 0, 0])
    assert np.allclose(sample_track(tr, 0.5), [1, 1, 1])


def test_rotation_uses_slerp():
    q90 = mu.axis_angle_quat([0, 1, 0], np.pi / 2)
    tr = Track(np.array([0.0, 1.0]), np.array([[0, 0, 0, 1.0], q90]), "LINEAR")
    assert np.allclose(sample_track(tr, 0.5), mu.axis_angle_quat([0, 1, 0], np.pi / 4))


def test_loop_time():
    assert loop_time(2.5, 1.0) == pytest.approx(0.5)
    assert loop_time(3.0, 0.0) == 0.0


def test_hips_ratio(model_path, anim_path):
    model, clip = load_glb(model_path), load_glb(anim_path).clips[0]
    assert hips_ratio(model.skeleton, clip) == pytest.approx(100)


def test_apply_clip(model_path, anim_path):
    model, clip = load_glb(model_path), load_glb(anim_path).clips[0]
    sk = model.skeleton
    pose = sk.rest_pose()
    apply_clip(clip, sk, pose, 0.5, hips_ratio(sk, clip))
    assert np.allclose(pose.t[sk.index("Hips")], [0, 150, 0])          # translation Hips mise à l'échelle
    assert np.allclose(pose.t[sk.index("Spine")], [0, 10, 0])          # translation de repos conservée
    assert np.allclose(pose.r[sk.index("Spine")], mu.axis_angle_quat([0, 1, 0], np.pi / 4))
    g = sk.global_matrices(pose)
    assert np.allclose(g[sk.index("Hips")][:3, 3], [0, 1.5, 0])
