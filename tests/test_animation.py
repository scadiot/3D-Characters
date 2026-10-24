import numpy as np
import pytest

from viewer import mathutil as mu
from viewer.animation import AnimationClip, Retargeter, Track, loop_time, sample_pose, sample_track
from viewer.gltf_loader import load_glb
from viewer.skeleton import Skeleton

LIN = Track(np.array([0.0, 1.0]), np.array([[0, 1, 0], [0, 2, 0.0]]), "LINEAR")
IDENTITY = [0, 0, 0, 1.0]


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


def test_sample_pose_on_source_skeleton(anim_path):
    clip = load_glb(anim_path).clips[0]
    pose = sample_pose(clip, 0.5)
    sk = clip.skeleton
    assert np.allclose(pose.t[sk.index("Hips")], [0, 1.5, 0])
    assert np.allclose(pose.r[sk.index("Spine")], mu.axis_angle_quat([0, 1, 0], np.pi / 4))


def test_retarget_fixture(model_path, anim_path):
    model, clip = load_glb(model_path), load_glb(anim_path).clips[0]
    sk = model.skeleton
    pose = Retargeter(sk, clip).pose(0.5)
    assert np.allclose(pose.t[sk.index("Hips")], [0, 150, 0])          # espace du parent (échelle 0.01)
    assert np.allclose(pose.t[sk.index("Spine")], [0, 10, 0])          # translation de repos conservée
    assert np.allclose(pose.r[sk.index("Spine")], mu.axis_angle_quat([0, 1, 0], np.pi / 4))
    g = sk.global_matrices(pose)
    assert np.allclose(g[sk.index("Hips")][:3, 3], [0, 1.5, 0])


def _skeleton(hips_r, spine_t, spine_r, hips_y=1.0) -> Skeleton:
    return Skeleton(
        names=["Hips", "Spine"], raw_names=["Hips", "Spine"], parents=np.array([-1, 0]),
        rest_t=np.array([[0, hips_y, 0], spine_t], dtype=float),
        rest_r=np.array([hips_r, spine_r], dtype=float), rest_s=np.ones((2, 3)),
    )


def _rotation(m: np.ndarray) -> np.ndarray:
    return m[:3, :3] / np.linalg.norm(m[:3, :3], axis=0)


def _clip(source: Skeleton) -> AnimationClip:
    y90 = mu.axis_angle_quat([0, 1, 0], np.pi / 2)
    one = np.array([0.0])
    return AnimationClip(
        name="test", duration=0.0,
        rotations={"Hips": Track(one, np.array([y90]), "LINEAR"),
                   "Spine": Track(one, np.array([y90]), "LINEAR")},
        translations={"Hips": Track(one, np.array([[0, 1.5, 0]]), "LINEAR")},
        skeleton=source,
    )


def test_retarget_handles_different_rest_axes():
    # Source : axes alignés sur le monde. Modèle : Hips tournées de -90° sur X (export Blender),
    # Spine compensée de +90° : même T-pose en monde, axes locaux différents.
    source = _skeleton(IDENTITY, [0, 0.1, 0], IDENTITY)
    model = _skeleton(mu.axis_angle_quat([1, 0, 0], -np.pi / 2), [0, 0, 0.1], mu.axis_angle_quat([1, 0, 0], np.pi / 2))
    clip = _clip(source)
    gs = source.global_matrices(sample_pose(clip, 0))
    gm = model.global_matrices(Retargeter(model, clip).pose(0))
    rest = model.global_matrices(model.rest_pose())
    ry90 = mu.quat_to_mat3(mu.axis_angle_quat([0, 1, 0], np.pi / 2))
    assert np.allclose(_rotation(gm[0]), ry90 @ _rotation(rest[0]))  # Hips : même delta monde que la source
    assert np.allclose(_rotation(gm[1]), _rotation(gs[1]))           # Spine : même orientation monde
    assert np.allclose(gm[0][:3, 3], [0, 1.5, 0])
    assert np.allclose(gm[1][:3, 3], gs[1][:3, 3])


def test_retarget_scales_hips_motion_by_height():
    source = _skeleton(IDENTITY, [0, 0.1, 0], IDENTITY)
    model = _skeleton(IDENTITY, [0, 0.2, 0], IDENTITY, hips_y=2.0)
    gm = model.global_matrices(Retargeter(model, _clip(source)).pose(0))
    assert np.allclose(gm[0][:3, 3], [0, 3.0, 0])  # +0.5 côté source × (2 / 1)
