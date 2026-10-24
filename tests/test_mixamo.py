import pytest

from viewer.gltf_loader import load_glb
from viewer.mixamo import normalize, validate


@pytest.mark.parametrize("raw", ["mixamorig:Hips", "mixamorig1:Hips", "mixamorig12:Hips", "mixamorig_Hips", "Hips"])
def test_normalize_strips_prefix(raw):
    assert normalize(raw) == "Hips"


def test_normalize_keeps_unknown_names():
    assert normalize("Armature") == "Armature"
    assert normalize("Bip01_Spine") == "Bip01_Spine"


def test_validate_explicit_names():
    r = validate({"Hips", "Spine", "Foo"}, {"Hips", "Bar"})
    assert "Spine1" in r.missing_core and "LeftHandIndex1" in r.missing_optional
    assert r.unknown_bones == ["Foo"]
    assert r.unmatched_tracks == ["Bar"]
    assert r.unanimated == ["Foo", "Spine"]
    assert r.warnings == len(r.missing_core) + 1 and not r.ok


def test_validate_without_clip():
    r = validate({"Hips"})
    assert r.unmatched_tracks == [] and r.unanimated == []


def test_validate_fixtures(model_path, anim_path):
    model, clip = load_glb(model_path), load_glb(anim_path).clips[0]
    r = validate(model.joint_names(), clip.track_names())
    assert r.unmatched_tracks == ["Ghost"] and r.unanimated == []


def test_details_text():
    assert "Ghost" in validate({"Hips"}, {"Ghost"}).details()
