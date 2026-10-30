import json

import pytest

from viewer.sprites.config import AnimationExport, ExportConfig, load_config, save_config


def test_round_trip(tmp_path):
    path = tmp_path / "spritesheet.json"
    cfg = ExportConfig(800, 200, [AnimationExport("walk", 10, ["S", "E"]), AnimationExport("pack / Idle", 1, ["N"])])
    save_config(path, cfg)
    loaded, error = load_config(path)
    assert error is None and loaded == cfg
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["animations"][0] == {"name": "walk", "frames": 10, "orientations": ["S", "E"]}


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
        "animations": [{"name": "walk", "frames": 500, "orientations": ["O", "X", "S", "S"]}, {"frames": 3}],
    }), encoding="utf-8")
    cfg, error = load_config(path)
    assert error is None
    assert (cfg.sheet_width, cfg.frame_height) == (64, 2048)
    assert cfg.animations == [AnimationExport("walk", 240, ["S", "O"])]


def test_legacy_fps_key_is_read_as_frame_count(tmp_path):
    path = tmp_path / "spritesheet.json"
    path.write_text(json.dumps({"animations": [{"name": "idle", "fps": 1, "orientations": ["S"]}]}), encoding="utf-8")
    cfg, _ = load_config(path)
    assert cfg.animations == [AnimationExport("idle", 1, ["S"])]


def test_time_range_round_trip(tmp_path):
    path = tmp_path / "spritesheet.json"
    cfg = ExportConfig(animations=[AnimationExport("golf", 12, ["S"], 0.5, 1.25), AnimationExport("walk", 8, ["S"], 0.2)])
    save_config(path, cfg)
    loaded, _ = load_config(path)
    assert loaded == cfg
    saved = json.loads(path.read_text(encoding="utf-8"))["animations"]
    assert (saved[0]["start"], saved[0]["end"]) == (0.5, 1.25)
    assert saved[1]["start"] == 0.2 and "end" not in saved[1]


def test_invalid_times_are_dropped(tmp_path):
    path = tmp_path / "spritesheet.json"
    path.write_text(json.dumps({"animations": [
        {"name": "a", "orientations": ["S"], "start": -1, "end": "x"},
        {"name": "b", "orientations": ["S"], "start": 2, "end": 1},
    ]}), encoding="utf-8")
    cfg, _ = load_config(path)
    assert [(a.start, a.end) for a in cfg.animations] == [(0.0, None), (2.0, None)]


@pytest.mark.parametrize("start,end,expected", [
    (0.0, None, (0.0, 2.0)),
    (0.5, 1.5, (0.5, 1.5)),
    (0.5, 9.0, (0.5, 2.0)),
    (3.0, None, (2.0, 2.0)),
    (1.5, 1.0, (1.5, 1.5)),
])
def test_time_range_is_clamped_to_clip(start, end, expected):
    assert AnimationExport("a", 8, ["S"], start, end).time_range(2.0) == expected
