import json

import numpy as np
import pytest

from viewer.attachments import (
    Attachment, apply_offset, compose, euler_quat, load_attachments, save_attachments, scan_objects, structure_key,
)
from viewer.gltf_loader import load_glb
from viewer.mathutil import quat_to_mat3
from viewer.player import Player, skinned_points


@pytest.fixture
def model(model_path):
    return load_glb(model_path)


@pytest.fixture
def objects(object_path):
    return {"tiny_object.glb": load_glb(object_path)}


def _unscaled(m: np.ndarray) -> np.ndarray:
    m = m.copy()
    m[:3, :3] /= np.linalg.norm(m[:3, :3], axis=0)
    return m


def _offset(a: Attachment) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = quat_to_mat3(euler_quat(a.rotation)) * a.scale
    m[:3, 3] = a.position
    return m


# --- config ---

def test_round_trip(tmp_path):
    path = tmp_path / "attachments.json"
    items = [Attachment("golf_club.glb", "RightHand", (0.0, 0.08, 0.02), (0.0, 0.0, 90.0), 1.5, False),
             Attachment("tools/hammer.glb")]
    save_attachments(path, items)
    loaded, error = load_attachments(path)
    assert error is None and loaded == items
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["attachments"][0] == {"object": "golf_club.glb", "bone": "RightHand", "position": [0.0, 0.08, 0.02],
                                       "rotation": [0.0, 0.0, 90.0], "scale": 1.5, "enabled": False}


def test_missing_file_gives_nothing(tmp_path):
    assert load_attachments(tmp_path / "nope.json") == ([], None)


def test_invalid_file_gives_message(tmp_path):
    path = tmp_path / "attachments.json"
    path.write_text("{oops", encoding="utf-8")
    items, error = load_attachments(path)
    assert items == [] and error


def test_values_are_cleaned(tmp_path):
    path = tmp_path / "attachments.json"
    path.write_text(json.dumps({"attachments": [
        {"object": "a.glb", "position": [1, "x"], "rotation": "oops", "scale": -2, "enabled": 0},
        {"bone": "Head"},
        "junk",
    ]}), encoding="utf-8")
    items, error = load_attachments(path)
    assert error is None
    assert items == [Attachment("a.glb", "RightHand", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0, False)]


def test_scan_objects(tmp_path):
    (tmp_path / "Objects" / "tools").mkdir(parents=True)
    for name in ("b.glb", "a.GLB", "tools/c.glb", "notes.txt"):
        (tmp_path / "Objects" / name).write_bytes(b"")
    assert scan_objects(tmp_path) == ["a.GLB", "b.glb", "tools/c.glb"]
    assert scan_objects(tmp_path / "missing") == []


# --- géométrie ---

def test_euler_order_is_x_then_y_then_z():
    m = quat_to_mat3(euler_quat((90, 90, 0)))
    # X puis Y : +Y -> +Z -> +X
    assert np.allclose(m @ [0, 1, 0], [1, 0, 0], atol=1e-9)


def test_compose_places_object_on_scaled_bone(model, objects):
    a = Attachment("tiny_object.glb", "Spine", (0.2, 0.0, 0.0), (0.0, 90.0, 0.0), 2.0)
    composed = compose(model, [a], objects)
    assert composed.messages == []
    sk = composed.model.skeleton
    n = len(model.skeleton.names)
    assert sk.names[n:] == ["attach0", "attach0/Root", "attach0/Stick"]
    assert sk.parents[n] == model.skeleton.index("Spine")
    assert list(sk.parents[n + 1:]) == [n, n + 1]
    (socket,) = composed.sockets
    assert socket.node == n and socket.attachment == 0 and socket.bone_scale == pytest.approx(0.01)

    p = Player()
    p.set_model(composed.model)
    g = p.frame().globals
    assert np.allclose(g[n], _unscaled(g[model.skeleton.index("Spine")]) @ _offset(a))
    # sommet (0, 0, 1) de l'objet : racine +0.5 Z, échelle 2, Y 90° (Z -> X), puis bone en (0, 1.1, 0)
    pts = skinned_points(composed.model, p.frame())
    assert np.allclose(pts[-1], [3.2, 1.1, 0.0])


def test_object_meshes_are_rigid_and_out_of_skins(model, objects):
    composed = compose(model, [Attachment("tiny_object.glb", "Hips")], objects)
    mesh = composed.model.meshes[-1]
    assert len(composed.model.meshes) == len(model.meshes) + 1
    assert mesh.skin is None and mesh.material is None
    assert mesh.node == composed.model.skeleton.index("attach0/Stick")
    assert composed.model.materials() == model.materials()
    assert composed.model.joint_names() == model.joint_names()


def test_object_follows_animated_bone(model, objects, anim_path):
    composed = compose(model, [Attachment("tiny_object.glb", "Spine", (0.0, 0.3, 0.0))], objects)
    p = Player()
    p.set_model(composed.model)
    p.set_clip(load_glb(anim_path).clips[0])
    p.seek(0.5)
    g = p.frame().globals
    spine, socket = model.skeleton.index("Spine"), composed.sockets[0].node
    assert not np.allclose(g[spine][:3, :3] / 0.01, np.eye(3))  # le bone a bien tourné
    assert np.allclose(g[socket], _unscaled(g[spine]) @ _offset(Attachment("x", position=(0.0, 0.3, 0.0))))


def test_bounds_include_object(model, objects):
    p = Player()
    p.set_model(compose(model, [Attachment("tiny_object.glb", "Hips")], objects).model)
    lo, hi = p.bounds()
    assert hi[2] == pytest.approx(1.5)


def test_skipped_entries(model, objects):
    items = [Attachment("tiny_object.glb", "Hips", enabled=False),
             Attachment("missing.glb", "Hips"),
             Attachment("tiny_object.glb", "Tail"),
             Attachment("tiny_object.glb", "Spine")]
    composed = compose(model, items, objects)
    assert [s.attachment for s in composed.sockets] == [3]
    assert len(composed.messages) == 2
    assert "missing.glb" in composed.messages[0] and "Tail" in composed.messages[1]
    assert composed.model.skeleton.names[len(model.skeleton.names)] == "attach3"


def test_no_attachment_keeps_model(model):
    assert compose(model, [], {}).model is model


def test_apply_offset_moves_socket_in_place(model, objects):
    a = Attachment("tiny_object.glb", "Spine")
    composed = compose(model, [a], objects)
    moved = Attachment("tiny_object.glb", "Spine", (0.0, 0.5, 0.0), (0.0, 0.0, 45.0), 3.0)
    apply_offset(composed.model, composed.sockets[0], moved)
    p = Player()
    p.set_model(composed.model)
    g = p.frame().globals
    assert np.allclose(g[composed.sockets[0].node], _unscaled(g[model.skeleton.index("Spine")]) @ _offset(moved))


def test_structure_key_ignores_offsets():
    a = Attachment("a.glb", "Head")
    b = Attachment("a.glb", "Head", (1.0, 0.0, 0.0), (0.0, 5.0, 0.0), 2.0)
    assert structure_key([a]) == structure_key([b])
    assert structure_key([a]) != structure_key([Attachment("a.glb", "Head", enabled=False)])
    assert structure_key([a]) != structure_key([Attachment("a.glb", "Neck")])
