import pytest

from viewer.mixamo import normalize


@pytest.mark.parametrize("raw", ["mixamorig:Hips", "mixamorig1:Hips", "mixamorig12:Hips", "mixamorig_Hips", "Hips"])
def test_normalize_strips_prefix(raw):
    assert normalize(raw) == "Hips"


def test_normalize_keeps_unknown_names():
    assert normalize("Armature") == "Armature"
    assert normalize("Bip01_Spine") == "Bip01_Spine"
