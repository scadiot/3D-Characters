import pytest

import glb_fixtures


@pytest.fixture(scope="session")
def glb_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("glb")
    glb_fixtures.build_model(d / "tiny_model.glb")
    glb_fixtures.build_anim(d / "tiny_anim.glb")
    glb_fixtures.build_object(d / "tiny_object.glb")
    return d


@pytest.fixture(scope="session")
def model_path(glb_dir):
    return glb_dir / "tiny_model.glb"


@pytest.fixture(scope="session")
def anim_path(glb_dir):
    return glb_dir / "tiny_anim.glb"


@pytest.fixture(scope="session")
def object_path(glb_dir):
    return glb_dir / "tiny_object.glb"
