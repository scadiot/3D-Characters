import json

import pytest

from viewer.sprites.layout import Placed, build_json
from viewer.sprites.sheet import list_exports, load_sheet, sheet_from_dict


def _frames(*xs):
    return [Placed(x, 0, 10, 50, 5, 46) for x in xs]


def _data():
    return build_json("Hero.png", 100, 50, 50, [
        {"name": "run", "orientation": "S", "fps": 4, "frames": _frames(0, 10, 20)},
        {"name": "idle", "orientation": "S", "fps": 0.4, "frames": _frames(30)},
        {"name": "run", "orientation": "E", "fps": 4, "frames": _frames(40, 50, 60)},
    ])


def test_groups_orientations_by_animation(tmp_path):
    sheet = sheet_from_dict(_data(), tmp_path / "Hero.json")
    assert sheet.image_path == tmp_path / "Hero.png"
    assert sheet.frame_height == 50
    assert [a.name for a in sheet.animations] == ["run", "idle"]
    run = sheet.animations[0]
    assert [s.orientation for s in run.sequences] == ["S", "E"]
    assert run.frame_count == 3
    assert run.sequences[1].frames[0].x == 40
    assert (run.sequences[0].frames[0].origin_x, run.sequences[0].frames[0].origin_y) == (5, 46)


@pytest.mark.parametrize("t,expected", [(0.0, 0), (0.24, 0), (0.25, 1), (0.6, 2), (0.75, 0), (1.3, 2)])
def test_frame_at_loops(tmp_path, t, expected):
    sequence = sheet_from_dict(_data(), tmp_path / "Hero.json").animations[0].sequences[0]
    assert sequence.index_at(t) == expected
    assert sequence.frame_at(t).x == 10 * expected


def test_zero_fps_shows_first_frame(tmp_path):
    data = _data()
    data["animations"][0]["fps"] = 0
    sequence = sheet_from_dict(data, tmp_path / "Hero.json").animations[0].sequences[0]
    assert sequence.index_at(12.0) == 0


def test_load_sheet_reports_invalid_files(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"image": "bad.png"}', encoding="utf-8")
    with pytest.raises(ValueError, match="bad.json"):
        load_sheet(path)
    path.write_text("pas du json", encoding="utf-8")
    with pytest.raises(ValueError, match="bad.json"):
        load_sheet(path)


def test_load_sheet_and_list_exports(tmp_path):
    (tmp_path / "b.json").write_text(json.dumps(_data()), encoding="utf-8")
    (tmp_path / "A.json").write_text(json.dumps(_data()), encoding="utf-8")
    (tmp_path / "A.png").write_bytes(b"")
    assert [p.name for p in list_exports(tmp_path)] == ["A.json", "b.json"]
    assert list_exports(tmp_path / "absent") == []
    assert len(load_sheet(tmp_path / "b.json").animations) == 2
