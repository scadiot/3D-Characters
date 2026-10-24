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
