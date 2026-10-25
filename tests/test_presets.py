import json

from viewer.attachments import Attachment, save_attachments
from viewer.presets import (
    DEFAULT_PRESET, Preset, check_name, delete_preset, list_presets, load_preset, preset_path, rename_preset,
    save_preset,
)
from viewer.sprites.config import AnimationExport, ExportConfig, save_config

GOLF = Preset(ExportConfig(800, 200, [AnimationExport("golf", 12, ["S", "E"])]),
              [Attachment("golf_club.glb", "RightHand", (0.0, 0.08, 0.0), (0.0, 0.0, 90.0))])


def test_round_trip(tmp_path):
    path = save_preset(tmp_path, "golf", GOLF)
    assert path == tmp_path / "exports" / "golf.json"
    assert load_preset(tmp_path, "golf") == (GOLF, None)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["sheetWidth"] == 800 and data["attachments"][0]["object"] == "golf_club.glb"


def test_list_is_sorted_without_case(tmp_path):
    for name in ("marche", "Golf", "base"):
        save_preset(tmp_path, name, Preset())
    (tmp_path / "exports" / "notes.txt").write_text("", encoding="utf-8")
    assert list_presets(tmp_path) == ["base", "Golf", "marche"]


def test_migration_from_legacy_files(tmp_path):
    save_config(tmp_path / "spritesheet.json", GOLF.export)
    save_attachments(tmp_path / "attachments.json", GOLF.attachments)
    assert list_presets(tmp_path) == [DEFAULT_PRESET]
    assert load_preset(tmp_path, DEFAULT_PRESET) == (GOLF, None)
    # dès qu'une config existe, les anciens fichiers ne sont plus lus
    save_preset(tmp_path, "base", Preset())
    assert list_presets(tmp_path) == ["base"]
    assert load_preset(tmp_path, DEFAULT_PRESET) == (Preset(), None)


def test_nothing_at_all_gives_default(tmp_path):
    assert list_presets(tmp_path) == [DEFAULT_PRESET]
    assert load_preset(tmp_path, DEFAULT_PRESET) == (Preset(), None)


def test_unreadable_file(tmp_path):
    save_preset(tmp_path, "golf", GOLF)
    preset_path(tmp_path, "golf").write_text("{oops", encoding="utf-8")
    preset, error = load_preset(tmp_path, "golf")
    assert preset == Preset() and "golf.json" in error


def test_rename_and_delete(tmp_path):
    save_preset(tmp_path, "golf", GOLF)
    rename_preset(tmp_path, "golf", "swing")
    assert list_presets(tmp_path) == ["swing"]
    assert load_preset(tmp_path, "swing")[0] == GOLF
    delete_preset(tmp_path, "swing")
    assert list_presets(tmp_path) == [DEFAULT_PRESET]


def test_rename_migrated_default_writes_it(tmp_path):
    save_config(tmp_path / "spritesheet.json", GOLF.export)
    rename_preset(tmp_path, DEFAULT_PRESET, "golf")
    assert list_presets(tmp_path) == ["golf"]
    assert load_preset(tmp_path, "golf")[0].export == GOLF.export
    assert (tmp_path / "spritesheet.json").is_file()  # ancien fichier conservé


def test_check_name():
    existing = ["golf", "Base"]
    assert check_name("marche", existing) is None
    assert check_name("", existing)
    assert check_name("a/b", existing) and check_name("what?", existing)
    assert check_name("fin.", existing)
    assert check_name("GOLF", existing)
    assert check_name("BASE", existing, current="Base") is None
