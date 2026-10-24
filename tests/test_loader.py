import numpy as np
import pytest

from viewer.gltf_loader import LoadError, clip_names, load_glb


def test_model_skeleton_names_are_canonical(model_path):
    f = load_glb(model_path)
    assert f.skeleton.names == ["Armature", "Hips", "Spine", "Body"]
    assert f.skeleton.raw_names[1] == "mixamorig:Hips"
    assert f.skeleton.parents.tolist() == [-1, 0, 1, -1]


def test_model_skin_and_mesh(model_path):
    f = load_glb(model_path)
    assert f.skinned
    assert f.skins[0].joints.tolist() == [1, 2]
    assert f.joint_names() == {"Hips", "Spine"}
    m = f.meshes[0]
    assert m.positions.shape == (4, 3) and m.indices.tolist() == [0, 1, 2, 0, 2, 3]
    assert m.joints.dtype == np.int32 and m.joints[:, 0].tolist() == [0, 0, 1, 1]
    assert m.skin == 0 and m.node == 3
    assert m.texture is not None and m.texture.size == (2, 2)
    assert f.clips == []


def test_anim_clip(anim_path):
    clip = load_glb(anim_path).clips[0]
    assert clip.name == "Take 001"
    assert clip.duration == pytest.approx(1.0)
    assert set(clip.rotations) == {"Spine", "Ghost"}
    assert set(clip.translations) == {"Hips"}
    assert clip.rotations["Ghost"].interpolation == "STEP"
    assert np.allclose(clip.hips_rest_t, [0, 1, 0])
    assert clip.track_names() == {"Hips", "Spine", "Ghost"}


def test_clip_names(anim_path, model_path):
    assert clip_names(anim_path) == ["Take 001"]
    assert clip_names(model_path) == []


@pytest.mark.parametrize("content", [b"not a glb at all", b"glTF" + b"\0" * 40])
def test_corrupt_file_raises_load_error(tmp_path, content):
    bad = tmp_path / "bad.glb"
    bad.write_bytes(content)
    with pytest.raises(LoadError):
        load_glb(bad)
