"""Golden tests: training paces must reproduce Daniels' Running Formula Table 5.2
(per-mile) exactly, with linear interpolation between integer VDOT rows."""

import pytest

from engine.paces import daniels_paces, training_paces, vdot_bounds

# Book Table 5.2 per-mile values (E range, M, T). Interval is the per-mile equivalent
# of the book's km/400 m split (e.g. VDOT 43 I = 4:26/km = 7:08/mi).
BOOK = {
    30: {"easy": "12:00-13:16", "marathon": "11:21", "threshold": "10:18", "interval": "9:31"},
    43: {"easy": "9:00-10:05", "marathon": "8:17", "threshold": "7:42", "interval": "7:08"},
    44: {"easy": "8:50-9:55", "marathon": "8:07", "threshold": "7:33", "interval": "7:00"},
    50: {"easy": "7:57-8:58", "marathon": "7:17", "threshold": "6:50", "interval": "6:18"},
    62: {"easy": "6:39-7:33", "marathon": "6:04", "threshold": "5:45", "interval": "5:17"},
}


@pytest.mark.parametrize("vdot,expected", BOOK.items())
def test_table_values_exact(vdot, expected):
    p = training_paces(vdot)
    for key, want in expected.items():
        assert p[key] == want, f"VDOT {vdot} {key}: got {p[key]}, want {want}"


def test_interpolation_midpoint():
    # VDOT 43 M=8:17 (497s), VDOT 44 M=8:07 (487s) -> 43.5 = 8:12 (492s)
    assert training_paces(43.5)["marathon"] == "8:12"
    assert training_paces(43.5)["threshold"] == "7:38"  # 7:42 / 7:33 midpoint


def test_clamps_outside_range():
    lo, hi = vdot_bounds()
    assert training_paces(lo - 5)["marathon"] == training_paces(lo)["marathon"]
    assert training_paces(hi + 5)["marathon"] == training_paces(hi)["marathon"]


def test_compat_shape():
    p = daniels_paces(43)
    assert p == {
        "Easy": "9:00-10:05",
        "Marathon": "8:17",
        "Threshold": "7:42",
        "Interval": "7:08",
        "Repetition": "6:34",
    }


def test_pace_zone_seconds_ordering_full_vdot_range():
    """Slower -> faster: Easy high > M > T > I > R (seconds per mile). Catches M/T inversion."""
    lo, hi = vdot_bounds()
    v = float(lo)
    while v <= hi + 1e-6:
        p = training_paces(v)
        e_hi = p["easy_high_s"]
        m, t, i_, r = p["marathon_s"], p["threshold_s"], p["interval_s"], p["rep_s"]
        assert e_hi is not None and m is not None and t is not None and i_ is not None, (
            f"VDOT {v}: missing core pace seconds"
        )
        assert e_hi > m > t > i_, f"VDOT {v}: easy_high {e_hi} M {m} T {t} I {i_}"
        if r is not None:
            assert i_ > r, f"VDOT {v}: interval {i_} rep {r}"
        v += 0.5
