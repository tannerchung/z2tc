"""Golden tests: VDOT from a race must reproduce Daniels' Table 5.1 (race time -> VDOT)
within rounding, across distances and the VDOT range the club spans."""

import pytest

from engine.vdot import vdot_from_race

HMS = lambda h, m, s: h * 3600 + m * 60 + s

# (label, distance_m, time_s, expected_vdot) from Table 5.1.
ANCHORS = [
    ("5K @40", 5000, HMS(0, 24, 8), 40),
    ("10K @40", 10000, HMS(0, 50, 3), 40),
    ("HM @40", 21097.5, HMS(1, 50, 59), 40),
    ("M @40", 42195, HMS(3, 49, 45), 40),
    ("5K @45", 5000, HMS(0, 21, 50), 45),
    ("10K @45", 10000, HMS(0, 45, 16), 45),
    ("HM @45", 21097.5, HMS(1, 40, 20), 45),
    ("5K @50", 5000, HMS(0, 19, 57), 50),
    ("10K @50", 10000, HMS(0, 41, 21), 50),
    ("HM @50", 21097.5, HMS(1, 31, 35), 50),
    ("M @50", 42195, HMS(3, 10, 49), 50),
]


@pytest.mark.parametrize("label,dist,secs,expected", ANCHORS)
def test_vdot_matches_book(label, dist, secs, expected):
    got = vdot_from_race(dist, secs)
    assert abs(got - expected) <= 0.3, f"{label}: got {got}, expected ~{expected}"


def test_kelly_brooklyn_half():
    # Doc S7 worked example: Brooklyn Half 1:43:58 sits between Table 5.1 VDOT 43
    # (1:44:20) and 44 (1:42:17), so ~43.
    got = vdot_from_race(21097.5, HMS(1, 43, 58))
    assert 42.7 <= got <= 43.6


def test_missing_inputs_return_none():
    assert vdot_from_race(0, 1200) is None
    assert vdot_from_race(5000, 0) is None
