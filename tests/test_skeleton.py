import pytest
import numpy as np

from viewer.gltf_loader import load_glb


def test_rest_pose_times_inverse_bind_is_identity(model_path):
    f = load_glb(model_path)
    g = f.skeleton.global_matrices(f.skeleton.rest_pose())
    skin = f.skins[0]
    for m in g[skin.joints] @ skin.inverse_bind:
        assert np.allclose(m, np.eye(4), atol=1e-6)


def test_global_positions(model_path):
    f = load_glb(model_path)
    g = f.skeleton.global_matrices(f.skeleton.rest_pose())
    assert np.allclose(g[1][:3, 3], [0, 1, 0])
    assert np.allclose(g[2][:3, 3], [0, 1.1, 0])


def test_index_lookup(model_path):
    sk = load_glb(model_path).skeleton
    assert sk.index("Spine") == 2 and sk.index("Nope") is None


def _legs(root_yaw: float):
    from viewer import mathutil as mu
    from viewer.skeleton import Skeleton
    return Skeleton(
        names=["Hips", "Spine", "LeftUpLeg", "RightUpLeg"], raw_names=["Hips", "Spine", "LeftUpLeg", "RightUpLeg"],
        parents=np.array([-1, 0, 0, 0]),
        rest_t=np.array([[0, 1, 0], [0, 0.1, 0], [0.1, -0.05, 0], [-0.1, -0.05, 0]], dtype=float),
        rest_r=np.array([mu.axis_angle_quat([0, 1, 0], root_yaw), [0, 0, 0, 1], [0, 0, 0, 1], [0, 0, 0, 1]]),
        rest_s=np.ones((4, 3)),
    )


def test_facing_yaw():
    assert abs(_legs(0).facing_yaw()) < 1e-9
    assert abs(abs(_legs(np.pi).facing_yaw()) - np.pi) < 1e-9
    assert _legs(np.pi / 2).facing_yaw() == pytest.approx(np.pi / 2)


def test_facing_yaw_without_sides_is_zero(model_path):
    assert load_glb(model_path).skeleton.facing_yaw() == 0.0
