import pytest

from viewer.sprites.layout import ANGLES, MARGIN, ORIENTATIONS, Placed, build_json, compute_scale, frame_times, pack


def test_orientations_and_angles():
    assert ORIENTATIONS == ("S", "SE", "E", "NE", "N", "NO", "O", "SO")
    assert [ANGLES[o] for o in ORIENTATIONS] == [0, 45, 90, 135, 180, 225, 270, 315]


@pytest.mark.parametrize("duration,fps,expected", [
    (1.0, 4, [0, 0.25, 0.5, 0.75]),
    (0.0, 12, [0.0]),
    (0.01, 12, [0.0]),  # round(0.12) = 0 -> au moins une frame
    (1.04, 10, [i / 10 for i in range(10)]),
])
def test_frame_times(duration, fps, expected):
    assert frame_times(duration, fps) == pytest.approx(expected)


def test_compute_scale():
    s = compute_scale(top=2.0, bottom=0.0, frame_height=250)
    assert s.pixels_per_unit == pytest.approx((250 - 2 * MARGIN) / 2.0)
    assert s.ground_y == pytest.approx(MARGIN + 2.0 * s.pixels_per_unit)
    below = compute_scale(top=2.0, bottom=-0.5, frame_height=250)
    assert below.pixels_per_unit == pytest.approx((250 - 2 * MARGIN) / 2.5)


def test_pack_new_row_per_sequence_and_wrap():
    seqs = [
        [(40, 20, 240)] * 3,  # 120 px : tient sur une ligne
        [(60, 30, 240)] * 4,  # 240 px > 200 : retour à la ligne après 3
    ]
    placed, height = pack(seqs, sheet_width=200, frame_height=250)
    assert [(p.x, p.y) for p in placed[0]] == [(0, 0), (40, 0), (80, 0)]
    assert [(p.x, p.y) for p in placed[1]] == [(0, 250), (60, 250), (120, 250), (0, 500)]
    assert placed[1][0] == Placed(0, 250, 60, 250, 30, 240)
    assert height == 750


def test_pack_rejects_too_wide_frame():
    with pytest.raises(ValueError):
        pack([[(300, 0, 0)]], sheet_width=200, frame_height=250)


def test_pack_empty():
    assert pack([], 200, 250) == ([], 0)


def test_build_json():
    frames = [Placed(0, 0, 83, 250, 41, 238)]
    data = build_json("Soldier.png", 1000, 250, 250,
                      [{"name": "walk", "orientation": "SE", "fps": 12, "frames": frames}])
    assert data == {
        "image": "Soldier.png", "width": 1000, "height": 250, "frameHeight": 250,
        "animations": [{
            "name": "walk", "orientation": "SE", "angle": 45, "fps": 12,
            "frames": [{"x": 0, "y": 0, "width": 83, "height": 250, "origin": {"x": 41, "y": 238}}],
        }],
    }
