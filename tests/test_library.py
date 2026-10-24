import shutil

from viewer import library
from viewer.library import scan


def _tree(root, model_path, anim_path):
    soldat = root / "Characters" / "soldat"
    (soldat / "skins").mkdir(parents=True)
    shutil.copy(model_path, soldat / "soldat.glb")
    (soldat / "skins" / "rouge.png").write_bytes(b"x")
    (soldat / "skins" / "bleu.jpg").write_bytes(b"x")
    (soldat / "skins" / "notes.txt").write_bytes(b"x")
    zombie = root / "Characters" / "zombie"
    zombie.mkdir()
    shutil.copy(model_path, zombie / "other.glb")
    (root / "Characters" / "empty").mkdir()
    (root / "Animations").mkdir()
    shutil.copy(anim_path, root / "Animations" / "run.glb")
    (root / "Animations" / "broken.glb").write_bytes(b"garbage")


def test_scan(tmp_path, model_path, anim_path):
    _tree(tmp_path, model_path, anim_path)
    lib = scan(tmp_path)
    assert [c.name for c in lib.characters] == ["soldat", "zombie"]
    assert [p.name for p in lib.characters[0].skins] == ["bleu.jpg", "rouge.png"]
    assert lib.characters[1].model_path.name == "other.glb"
    assert [a.label for a in lib.animations] == ["broken", "run"]
    assert lib.animations[0].error and lib.animations[1].error is None
    assert any("empty" in m for m in lib.messages)


def test_multi_clip_labels(tmp_path, monkeypatch):
    (tmp_path / "Characters").mkdir()
    (tmp_path / "Animations").mkdir()
    (tmp_path / "Animations" / "pack.glb").write_bytes(b"x")
    monkeypatch.setattr(library, "clip_names", lambda p: ["Idle", "Walk"])
    lib = scan(tmp_path)
    assert [(a.label, a.clip_index) for a in lib.animations] == [("pack / Idle", 0), ("pack / Walk", 1)]


def test_missing_folders(tmp_path):
    lib = scan(tmp_path)
    assert lib.characters == [] and lib.animations == [] and len(lib.messages) == 2


def test_loose_glb_files_are_characters(tmp_path, model_path):
    shutil.copy(model_path, tmp_path / "Michelle.glb")
    (tmp_path / "Characters").mkdir()
    shutil.copy(model_path, tmp_path / "Characters" / "Xbot.glb")
    lib = scan(tmp_path)
    assert [(c.name, c.model_path.name, c.skins) for c in lib.characters] == [
        ("Michelle", "Michelle.glb", []), ("Xbot", "Xbot.glb", [])]


def test_flat_folder_without_subfolders_has_no_missing_folder_messages(tmp_path, model_path):
    shutil.copy(model_path, tmp_path / "Michelle.glb")
    lib = scan(tmp_path)
    assert [c.name for c in lib.characters] == ["Michelle"] and lib.messages == []
