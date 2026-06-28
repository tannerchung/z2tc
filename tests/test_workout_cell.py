"""Cell rendering for plan calendar labels (:mod:`render.workout_cell`).

Locks the grid-method (Pfitzinger/Hansons/Higdon) handling: their labels name the work in the
book's words and carry the concrete pace on the Workout, so the cell must fold that pace in and
stack the session — the same executable card the Daniels recipes already produce.
"""

from __future__ import annotations

from render.workout_cell import format_cell


def test_daniels_recipe_unchanged():
    out = format_cell(
        "Cruise intervals: 1.5 mi easy warm-up → 4 x 0.9 mi @ Threshold (7:41/mi) "
        "w/ 60 s jog → 1.5 mi easy cool-down",
        pace="7:41",
    )
    assert out.startswith("Cruise Intervals")
    assert "Warm-up: 1.5 mi easy" in out
    assert "4 × 0.9 mi @ Threshold (7:41), 60s jog" in out
    assert "Cool-down: 1.5 mi easy" in out


def test_pfitz_threshold_folds_in_pace():
    out = format_cell(
        "Lactate threshold 10 mi w/ 5 mi @ 15K to half marathon race pace", pace="6:55"
    )
    assert out.startswith("Lactate Threshold — 10 mi")
    # Canonical zone leads (so the cell colors as threshold), book phrasing kept as the descriptor.
    assert "5 mi @ Threshold (15K–half pace, 6:55)" in out
    # 10 mi total − 5 mi at threshold = 5 mi easy, split evenly as explicit warm-up + cool-down.
    assert "Warm-up: 2.5 mi easy" in out
    assert "Cool-down: 2.5 mi easy" in out


def test_pfitz_marathon_pace_run():
    out = format_cell("Marathon-pace run 13 mi w/ 8 mi @ marathon race pace", pace="7:15")
    assert out.startswith("Marathon-pace Run — 13 mi")
    assert "8 mi @ Marathon pace (7:15)" in out
    assert "Warm-up: 2.5 mi easy" in out
    assert "Cool-down: 2.5 mi easy" in out


def test_pfitz_vo2max_intervals_with_recovery():
    out = format_cell(
        "VO₂max 10 mi w/ 4 x 1,200 m @ 5K race pace; jog 50 to 90% interval time between",
        pace="6:24",
    )
    assert out.startswith("VO₂max — 10 mi")
    assert "4 × 1,200 m @ VO2max (5K pace, 6:24)" in out
    assert "jog 50–90% interval time between" in out
    # Rep work: jog recoveries also live in the total, so the warm-up/cool-down lines carry no figure.
    assert "Warm-up: easy" in out
    assert "Cool-down: easy" in out


def test_pfitz_general_aerobic_plus_speed_pm():
    out = format_cell("General aerobic + speed 7 mi w/ 8 x 100 m strides p.m.", pace="8:34")
    assert out.startswith("General Aerobic + Speed — 7 mi")
    assert "@ Easy (8:34)" in out
    assert "+ 8 × 100 m strides" in out
    assert "(second run, p.m.)" in out


def test_plain_general_aerobic_and_medium_long_get_easy_pace():
    assert "@ Easy (8:34)" in format_cell("General aerobic 10 mi", pace="8:34")
    ml = format_cell("Medium-long run 12 mi", pace="9:16")
    assert ml.startswith("Medium-long Run — 12 mi")
    assert "@ Easy (9:16)" in ml


def test_tune_up_race_not_mangled():
    out = format_cell("8K-15K tune-up race (total 9-13 mi) (11 mi)", pace=None)
    assert out.startswith("8K–15K Tune-up Race")
    assert "total 9–13 mi" in out
    assert "(total" not in out  # no leftover raw fragment


def test_pace_optional_falls_back_gracefully():
    out = format_cell("Lactate threshold 8 mi w/ 4 mi @ 15K to half marathon race pace")
    assert "4 mi @ Threshold (15K–half pace)" in out
    assert "()" not in out  # no empty pace parens when pace is absent


def test_rest_and_blank_passthrough():
    assert format_cell("Rest Day") == "Rest Day"
    assert format_cell("") == ""
