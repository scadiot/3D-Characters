import json

from viewer.sprites.config import AnimationExport, ExportConfig, load_config, save_config


def test_round_trip(tmp_path):
    path = tmp_path / "spritesheet.json"
    cfg = ExportConfig(800, 200, [AnimationExport("walk", 10, ["S", "E"]), AnimationExport("pack / Idle", 24, ["N"])])
    save_config(path, cfg)
    loaded, error = load_config(path)
    assert error is None and loaded == cfg
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["animations"][0] == {"name": "walk", "fps": 10, "orientations": ["S", "E"]}


def test_missing_file_gives_defaults(tmp_path):
    cfg, error = load_config(tmp_path / "nope.json")
    assert error is None and cfg == ExportConfig()
    assert (cfg.sheet_width, cfg.frame_height, cfg.animations) == (1000, 250, [])


def test_invalid_file_gives_defaults_and_message(tmp_path):
    path = tmp_path / "spritesheet.json"
    path.write_text("{oops", encoding="utf-8")
    cfg, error = load_config(path)
    assert cfg == ExportConfig() and error


def test_values_are_cleaned(tmp_path):
    path = tmp_path / "spritesheet.json"
    path.write_text(json.dumps({
        "sheetWidth": 10, "frameHeight": 99999,
        "animations": [{"name": "walk", "fps": 500, "orientations": ["O", "X", "S", "S"]}, {"fps": 3}],
    }), encoding="utf-8")
    cfg, error = load_config(path)
    assert error is None
    assert (cfg.sheet_width, cfg.frame_height) == (64, 2048)
    assert cfg.animations == [AnimationExport("walk", 60, ["S", "O"])]
