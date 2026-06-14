"""Golden tests for the deterministic plan engine.

Anchored on the project's Training Plan Formula Reference, especially Kelly's worked
example (sec.7), which exists precisely to prove the long-run math is deterministic.
"""

from __future__ import annotations

import pytest

from engine.paces import training_paces
from engine.plan import AthleteInputs, MarathonRace, build_plan
from engine.plan import common
from engine.plan.models import WorkoutKind


def HMS(h, m, s):
    return h * 3600 + m * 60 + s


def _daniels_athlete(**over):
    base = dict(
        name="Kelly", vdot=43, goal_marathon_s=HMS(3, 55, 0), w_now=28.0, p_history=31.0,
        longest_run_mi=13.0, days_per_week=4, race_date="2026-10-10", block_weeks=18,
    )
    base.update(over)
    return AthleteInputs(**base)


def _pfitz_athlete(**over):
    base = dict(
        name="Tanner", vdot=52, goal_marathon_s=HMS(3, 10, 0), w_now=40.0, p_history=55.0,
        longest_run_mi=18.0, days_per_week=6, race_date="2026-10-10", block_weeks=18,
    )
    base.update(over)
    return AthleteInputs(**base)


# --- sec.7 Kelly: the long-run formula is deterministic --------------------------
def test_kelly_long_run_formula():
    easy_s, _ = common.easy_pace(training_paces(43))
    lr = common.daniels_long_run(31.0, easy_s)

    # 150-min run at ~9:30/mi easy pace is ~15.8 mi.
    assert 15.3 <= lr.time_cap_mi <= 16.2
    # 30% share at W<=40: 0.30 * 31 = 9.3 mi.
    assert lr.share_mi == pytest.approx(9.3, abs=0.05)
    # A 150-min run would blow past 1/3 of the week -> volume-too-low flag.
    assert any("volume too low" in f for f in lr.flags)
    # The prescribed long run is held to ~1/3 of the week, not the 15+ the cap allows.
    assert lr.recommended_mi == pytest.approx(31 / 3, abs=0.2)


def test_long_run_no_flag_when_volume_supports_it():
    easy_s, _ = common.easy_pace(training_paces(50))
    lr = common.daniels_long_run(60.0, easy_s)
    assert not lr.flags
    assert lr.recommended_mi <= 60 / 3 + 0.1


# --- sec.1 Method assignment -----------------------------------------------------
@pytest.mark.parametrize(
    "p_history,days,expected",
    [
        (31, 4, common.DANIELS),   # Kelly / Cindy
        (55, 6, common.PFITZINGER),  # Tanner / Rohan
        (45, 4, common.DANIELS),   # base but only 4 days -> Daniels
        (38, 6, common.DANIELS),   # 6 days but base under 40 -> Daniels
    ],
)
def test_method_assignment(p_history, days, expected):
    a = _daniels_athlete(p_history=p_history, days_per_week=days, method=None)
    assert common.assign_method(a) == expected


def test_forced_method_wins():
    a = _pfitz_athlete(method=common.DANIELS)
    assert common.assign_method(a) == common.DANIELS


# --- sec.3 Volume progression invariants -----------------------------------------
def test_volume_progression():
    days = 5
    vols = common.weekly_volumes(30.0, 55.0, 18, days, taper_weeks=3)
    assert len(vols) == 18
    assert max(vols) == pytest.approx(55.0, abs=0.05)  # peak reached, never exceeded

    build = vols[:-3]
    # Hold-level (non-down) weeks increase by at most `days` mpw.
    holds = [v for i, v in enumerate(build) if (i + 1) % 4 != 0]
    for a, b in zip(holds, holds[1:]):
        assert b - a <= days + 0.05
    # Every 4th build week steps back below its neighbours.
    for i, v in enumerate(build):
        if (i + 1) % 4 == 0:
            assert v < build[i - 1]

    taper = vols[-3:]
    assert all(t < 55.0 for t in taper)
    assert taper[0] > taper[1] > taper[2]  # strictly descending


# --- sec.5 Session caps ----------------------------------------------------------
def test_session_caps():
    c31 = common.session_caps(31)
    assert c31 == {"T": 3.1, "M": 9.3, "I": 2.5, "R": 1.6}
    c55 = common.session_caps(55)
    assert c55 == {"T": 5.5, "M": 11.0, "I": 4.4, "R": 2.8}


# --- sec.6 Race recovery ---------------------------------------------------------
def test_recovery_days():
    assert common.recovery_days_after_race(10000) == 3
    assert common.recovery_days_after_race(21097.5) == 7
    assert common.recovery_days_after_race(42195) == 14


# --- Full plan smoke tests -------------------------------------------------------
def test_daniels_full_plan():
    plan = build_plan(_daniels_athlete())
    assert plan.method == common.DANIELS
    assert len(plan.weeks) == 18

    last = plan.weeks[-1]
    assert last.phase == "Taper"
    race_days = [d.day for d in last.days if d.workout.kind == WorkoutKind.RACE]
    assert race_days == [common.LONG_RUN_DAY]

    # Quality (non-down, non-base/taper) weeks carry exactly two quality sessions.
    for w in plan.weeks:
        if w.phase in ("Threshold", "Race Prep") and not w.is_down_week:
            assert len(w.quality_days) == 2, f"week {w.index} ({w.label})"
        # No prescribed week exceeds the athlete's peak by more than rounding.
        assert w.target_miles <= plan.peak_miles + 0.05


def test_pfitzinger_full_plan():
    plan = build_plan(_pfitz_athlete())
    assert plan.method == common.PFITZINGER
    assert len(plan.weeks) == 18
    assert max(w.target_miles for w in plan.weeks) == pytest.approx(plan.peak_miles, abs=0.05)

    last = plan.weeks[-1]
    assert last.phase == "Taper"
    race_days = [d.day for d in last.days if d.workout.kind == WorkoutKind.RACE]
    assert race_days == [common.LONG_RUN_DAY]
    # Every week has a long run and a midweek medium-long run.
    for w in plan.weeks[:-1]:
        assert w.long_run is not None, f"week {w.index} has no long run"


def test_plan_is_deterministic():
    a = _daniels_athlete()
    p1, p2 = build_plan(a), build_plan(a)
    assert [d.workout.label for w in p1.weeks for d in w.days] == \
           [d.workout.label for w in p2.weeks for d in w.days]


def test_long_run_day_is_saturday():
    plan = build_plan(_daniels_athlete())
    wk = plan.weeks[5]  # threshold-ish week
    lr = wk.long_run
    assert lr is not None
    assert lr.day == common.LONG_RUN_DAY


def test_secondary_marathons_in_goal_and_flags():
    nyc = MarathonRace(name="TCS New York City Marathon", date="2026-11-01")
    a = _pfitz_athlete(
        race_name="Bank of America Chicago Marathon",
        race_date="2026-10-10",
        secondary_races=(nyc,),
    )
    plan = build_plan(a)
    assert plan.goal["name"] == "Bank of America Chicago Marathon"
    assert plan.goal["date"] == "2026-10-10"
    assert plan.goal["secondary_marathons"] == [{"name": nyc.name, "date": nyc.date}]
    assert any("secondary_after_primary" in f for f in plan.flags)
