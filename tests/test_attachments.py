import json

import numpy as np
import pytest

from viewer.attachments import (
    Attachment, apply_offset, compose, load_placement, offset_matrix, placement_path, save_placement, scan_objects,
    structure_key,
)
from viewer.gltf_loader import load_glb
from viewer.mathutil import axis_angle_quat
from viewer.player import Player, skinned_points


@pytest.fixture
def model(model_path):
    return load_glb(model_path)


@pytest.fixture
def objects(object_path):
    return {"tiny_object.glb": load_glb(object_path)}


def _rest_frame(g_bone: np.ndarray, g_bone_rest: np.ndarray) -> np.ndarray:
    """Repère T-pose déplacé avec le bone : origine sur le bone, rotation = variation depuis la T-pose."""
    m = np.eye(4)
    m[:3, :3] = g_bone[:3, :3] @ np.linalg.inv(g_bone_rest[:3, :3])
    m[:3, 3] = g_bone[:3, 3]
    return m


# --- réglages des objets ---

def test_placement_round_trip(tmp_path):
    (tmp_path / "Objects" / "tools").mkdir(parents=True)
    a = Attachment("tools/golf_club.glb", "LeftHand", (0.0, 0.08, 0.02), (0.0, 0.0, 90.0), 1.5)
    path = save_placement(tmp_path, a)
    assert path == tmp_path / "Objects" / "tools" / "golf_club.json" == placement_path(tmp_path, a.object)
    assert load_placement(tmp_path, a.object) == (a, None)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "bone": "LeftHand", "position": [0.0, 0.08, 0.02], "rotation": [0.0, 0.0, 90.0], "scale": 1.5}


def test_missing_placement_gives_defaults(tmp_path):
    assert load_placement(tmp_path, "club.glb") == (Attachment("club.glb"), None)


def test_invalid_placement_gives_message(tmp_path):
    (tmp_path / "Objects").mkdir()
    placement_path(tmp_path, "club.glb").write_text("{oops", encoding="utf-8")
    a, error = load_placement(tmp_path, "club.glb")
    assert a == Attachment("club.glb") and "club.json" in error


def test_placement_values_are_cleaned(tmp_path):
    (tmp_path / "Objects").mkdir()
    placement_path(tmp_path, "a.glb").write_text(json.dumps(
        {"bone": "", "position": [1, "x"], "rotation": "oops", "scale": -2}), encoding="utf-8")
    assert load_placement(tmp_path, "a.glb") == (Attachment("a.glb"), None)


def test_scan_objects(tmp_path):
    (tmp_path / "Objects" / "tools").mkdir(parents=True)
    for name in ("b.glb", "a.GLB", "tools/c.glb", "notes.txt", "b.json"):
        (tmp_path / "Objects" / name).write_bytes(b"")
    assert scan_objects(tmp_path) == ["a.GLB", "b.glb", "tools/c.glb"]
    assert scan_objects(tmp_path / "missing") == []


# --- géométrie ---

def test_euler_order_is_x_then_y_then_z():
    m = offset_matrix(Attachment("x", rotation=(90, 90, 0)))[:3, :3]
    # X puis Y : +Y -> +Z -> +X
    assert np.allclose(m @ [0, 1, 0], [1, 0, 0], atol=1e-9)


def test_compose_places_object_in_rest_frame_on_scaled_bone(model, objects):
    a = Attachment("tiny_object.glb", "Spine", (0.2, 0.0, 0.0), (0.0, 90.0, 0.0), 2.0)
    composed = compose(model, [a], objects)
    assert composed.messages == []
    sk = composed.model.skeleton
    n = len(model.skeleton.names)
    assert sk.names[n:] == ["attach0", "attach0/Root", "attach0/Stick"]
    assert sk.parents[n] == model.skeleton.index("Spine")
    assert list(sk.parents[n + 1:]) == [n, n + 1]
    assert [(s.attachment, s.node) for s in composed.sockets] == [(0, n)]

    p = Player()
    p.set_model(composed.model)
    g = p.frame().globals
    spine = g[model.skeleton.index("Spine")]
    assert np.allclose(g[n], _rest_frame(spine, spine) @ offset_matrix(a))
    # sommet (0, 0, 1) de l'objet : racine +0.5 Z, échelle 2, Y 90° (Z -> X), puis bone en (0, 1.1, 0)
    pts = skinned_points(composed.model, p.frame())
    assert np.allclose(pts[-1], [3.2, 1.1, 0.0])


def test_bone_axes_do_not_change_the_result(model, objects):
    """Deux rigs aux axes de bone différents donnent le même placement en T-pose."""
    a = Attachment("tiny_object.glb", "Spine", (0.1, 0.2, 0.3), (10.0, 20.0, 30.0), 1.5)
    reference = skinned_points(*_rest(compose(model, [a], objects).model))
    spine = model.skeleton.index("Spine")
    model.skeleton.rest_r[spine] = axis_angle_quat([1, 2, 3], 1.2)  # axes locaux tournés
    turned = skinned_points(*_rest(compose(model, [a], objects).model))
    assert np.allclose(turned[-3:], reference[-3:])


def _rest(model):
    p = Player()
    p.set_model(model)
    return model, p.frame()


def test_object_meshes_are_rigid_and_out_of_skins(model, objects):
    composed = compose(model, [Attachment("tiny_object.glb", "Hips")], objects)
    mesh = composed.model.meshes[-1]
    assert len(composed.model.meshes) == len(model.meshes) + 1
    assert mesh.skin is None and mesh.material is None
    assert mesh.node == composed.model.skeleton.index("attach0/Stick")
    assert composed.model.materials() == model.materials()
    assert composed.model.joint_names() == model.joint_names()


def test_object_follows_animated_bone(model, objects, anim_path):
    a = Attachment("tiny_object.glb", "Spine", (0.0, 0.3, 0.0), (0.0, 0.0, 45.0))
    composed = compose(model, [a], objects)
    p = Player()
    p.set_model(composed.model)
    rest = p.frame().globals
    p.set_clip(load_glb(anim_path).clips[0])
    p.seek(0.5)
    g = p.frame().globals
    spine, socket = model.skeleton.index("Spine"), composed.sockets[0].node
    assert not np.allclose(g[spine][:3, :3], rest[spine][:3, :3])  # le bone a bien tourné
    assert np.allclose(g[socket], _rest_frame(g[spine], rest[spine]) @ offset_matrix(a))


def test_bounds_include_object(model, objects):
    p = Player()
    p.set_model(compose(model, [Attachment("tiny_object.glb", "Hips")], objects).model)
    lo, hi = p.bounds()
    assert hi[2] == pytest.approx(1.5)


def test_skipped_entries(model, objects):
    items = [Attachment("missing.glb", "Hips"),
             Attachment("tiny_object.glb", "Tail"),
             Attachment("tiny_object.glb", "Spine")]
    composed = compose(model, items, objects)
    assert [s.attachment for s in composed.sockets] == [2]
    assert len(composed.messages) == 2
    assert "missing.glb" in composed.messages[0] and "Tail" in composed.messages[1]
    assert composed.model.skeleton.names[len(model.skeleton.names)] == "attach2"


def test_no_attachment_keeps_model(model):
    assert compose(model, [], {}).model is model


def test_apply_offset_moves_socket_in_place(model, objects):
    composed = compose(model, [Attachment("tiny_object.glb", "Spine")], objects)
    moved = Attachment("tiny_object.glb", "Spine", (0.0, 0.5, 0.0), (0.0, 0.0, 45.0), 3.0)
    apply_offset(composed.model, composed.sockets[0], moved)
    p = Player()
    p.set_model(composed.model)
    g = p.frame().globals
    spine = g[model.skeleton.index("Spine")]
    assert np.allclose(g[composed.sockets[0].node], _rest_frame(spine, spine) @ offset_matrix(moved))


def test_structure_key_ignores_offsets():
    a = Attachment("a.glb", "Head")
    b = Attachment("a.glb", "Head", (1.0, 0.0, 0.0), (0.0, 5.0, 0.0), 2.0)
    assert structure_key([a]) == structure_key([b])
    assert structure_key([a]) != structure_key([Attachment("a.glb", "Neck")])
    assert structure_key([a]) != structure_key([a, b])
