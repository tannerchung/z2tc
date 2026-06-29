"""Tests for the coach-facing readiness model (engine/readiness.py).

These lock the *shape* and book-anchored thresholds of the advisory layer (race-time
prediction, Table 15.1 breaks, diminishing-return projection, goal feasibility). The
heuristics are tunable, so tolerances are loose where the book gives no exact number.
"""

from __future__ import annotations

import pytest

from engine import readiness as rd
from engine.plan import AthleteInputs
from engine.vdot import RACE_METERS, predict_race_time, race_equivalent_times, vdot_from_race


def HMS(h, m, s):
    return h * 3600 + m * 60 + s


# --- Race-time prediction (inverse VDOT) -----------------------------------------
def test_predict_matches_daniels_table_vdot50():
    # Daniels Table 5.1 @ VDOT 50: 5K 19:57, 10K 41:21, HM 1:31:35, M 3:10:49.
    t = race_equivalent_times(50)
    assert t["5K"] == pytest.approx(HMS(0, 19, 57), abs=20)
    assert t["10K"] == pytest.approx(HMS(0, 41, 21), abs=25)
    assert t["Half Marathon"] == pytest.approx(HMS(1, 31, 35), abs=40)
    assert t["Marathon"] == pytest.approx(HMS(3, 10, 49), abs=60)


def test_predict_is_inverse_of_vdot_from_race():
    secs = predict_race_time(48, RACE_METERS["Half Marathon"])
    assert vdot_from_race(RACE_METERS["Half Marathon"], secs) == pytest.approx(48, abs=0.1)


# --- Table 15.1 break adjustment -------------------------------------------------
def test_break_adjustment_anchors():
    assert rd.break_adjustment_factor(5) == 1.0           # <=5 days: no loss
    assert rd.break_adjustment_factor(42) == pytest.approx(0.889, abs=0.005)   # 6 wk, no cross
    assert rd.break_adjustment_factor(42, True) == pytest.approx(0.944, abs=0.005)  # 6 wk + cross
    assert rd.break_adjustment_factor(120) == pytest.approx(0.80, abs=0.01)    # floor ~20% loss


def test_adjusted_vdot_only_for_real_break():
    assert rd.adjusted_vdot(50, 4) == 50.0                 # short break: unchanged
    assert rd.adjusted_vdot(50, 42) < 46                   # 6-wk break discounts fitness


def test_classify_cross_training():
    assert rd.classify_cross_training(["Ride", "WeightTraining"]) == "leg_aerobic"
    assert rd.classify_cross_training(["Pilates", "Yoga"]) == "strength_mobility"
    assert rd.classify_cross_training([]) == "none"


# --- Diminishing return ----------------------------------------------------------
def test_projected_gain_diminishes_with_fitness():
    low = rd.projected_vdot_gain(40, 15)
    high = rd.projected_vdot_gain(65, 15)
    assert low > high > 0   # fitter athlete gains less over the same block (Principle 6)


# --- Goal feasibility ------------------------------------------------------------
def test_goal_within_current_fitness():
    # A 3:45 marathon needs ~VDOT 41.7; a current 43 athlete is already there.
    g = rd.goal_feasibility(43.0, HMS(3, 45, 0))
    assert g.verdict == "within_current"
    assert g.gap_vdot <= 0


def test_unrealistic_goal_gets_alternative_time():
    # Sub-3 (needs ~VDOT 53) from a 40 VDOT base in 15 wk is unrealistic.
    g = rd.goal_feasibility(40.0, HMS(2, 59, 0))
    assert g.verdict in ("unrealistic", "stretch")
    assert g.realistic_time_s is not None and g.realistic_time_s > HMS(2, 59, 0)


# --- Volume readiness ------------------------------------------------------------
def test_reentry_midpoint_for_racefit_lowvolume():
    start, why = rd.recommended_reentry_volume(11.0, 48.0, race_fit=True)
    assert start == pytest.approx(24.0, abs=0.1)   # ~0.5 * p_history, not raw 11
    assert "midpoint" in why


def test_recommended_peak_respects_ceiling_and_injury():
    p, _ = rd.recommended_peak_mileage(95.0, 7)
    assert p == rd.DANIELS_MILEAGE_CEILING
    p2, _ = rd.recommended_peak_mileage(45.0, 5, injury_prone=True, goal_demanding=True)
    assert p2 == pytest.approx(45.0, abs=0.05)     # injury-prone holds at demonstrated


# --- Fitness selection from directives (Cindy-like) ------------------------------
def _cindy_races():
    return [
        {"category": "5K", "date": "2025-04-05", "duration_s": HMS(0, 27, 8)},
        {"category": "Half Marathon", "date": "2025-05-17", "duration_s": HMS(2, 4, 0)},
        {"category": "Marathon", "date": "2025-10-11", "duration_s": HMS(4, 0, 25)},
        {"category": "Half Marathon", "date": "2026-04-26", "duration_s": HMS(2, 8, 0)},
        {"category": "10K", "date": "2026-06-06", "duration_s": HMS(0, 58, 38)},
    ]


def test_select_drops_submaximal_races():
    # Without an anchor, tagging both off-season races submaximal drops them; the surviving
    # max half (Brooklyn) wins on Daniels preference, not the soft 2026 half.
    sel = rd.select_fitness_vdot(
        _cindy_races(),
        effort_quality={"2026-04-26": "submaximal", "2026-06-06": "submaximal"},
    )
    assert sel.chosen_date == "2025-05-17"
    assert any("2026-04-26" in d for d in sel.dropped)


def test_select_anchor_with_estimate_and_detrain():
    # Anchor the marathon with a coach estimate (3:55) + 28-day detraining → 36.2.
    sel = rd.select_fitness_vdot(
        _cindy_races(),
        time_overrides={"2025-10-11": HMS(3, 55, 0)},
        anchor_date="2025-10-11",
        break_days=28,
    )
    assert sel.race_vdot == pytest.approx(38.9, abs=0.1)
    assert sel.effective_vdot == pytest.approx(36.2, abs=0.1)
    assert "anchored" in sel.source


def test_select_excluded_race_removed():
    sel = rd.select_fitness_vdot(_cindy_races(), excluded_dates={"2025-05-17"})
    assert sel.chosen_date != "2025-05-17"


def _week(week_start: str, miles: float) -> dict:
  workouts = []
  if miles > 0:
      workouts = [{"sport_type": "Run", "stats": {"Distance": f"{miles} mi"}}]
  return {"week_start": week_start, "workouts": workouts}


def _cindy_offseason_weeks() -> list[dict]:
    """Running after Apr 2026 half; 4 zero weeks Dec 2025 (28d break since marathon)."""
    weeks: list[dict] = []
    # Oct 2025 – Mar 2026: light running except Dec off block
    for ws, mi in [
        ("2025-10-13", 15.0),
        ("2025-10-20", 12.0),
        ("2025-11-03", 10.0),
        ("2025-11-10", 8.0),
        ("2025-11-17", 6.0),
        ("2025-11-24", 4.0),
        ("2025-12-01", 0.0),
        ("2025-12-08", 0.0),
        ("2025-12-15", 0.0),
        ("2025-12-22", 0.0),
        ("2025-12-29", 5.0),
        ("2026-01-05", 8.0),
        ("2026-02-02", 12.0),
        ("2026-03-02", 14.0),
        ("2026-04-07", 16.0),
        ("2026-04-14", 18.0),
        ("2026-04-21", 20.0),
        ("2026-04-28", 15.0),
        ("2026-05-05", 16.0),
        ("2026-06-02", 16.0),
    ]:
        weeks.append(_week(ws, mi))
    return weeks


def test_resolve_merge_vdot_prefers_fitness_break_window():
    from datetime import date

    post_marathon_races = [
        {"category": "Half Marathon", "date": "2026-04-26", "duration_s": HMS(2, 8, 0)},
        {"category": "10K", "date": "2026-06-06", "duration_s": HMS(0, 58, 38)},
    ]
    res = rd.resolve_merge_vdot(
        post_marathon_races,
        _cindy_offseason_weeks(),
        marathon_date=date(2025, 10, 11),
        today=date(2026, 6, 15),
    )
    assert res is not None
    assert res.fitness.chosen_date == "2026-04-26"
    assert res.break_window == "fitness_race"
    assert res.break_days < 7
    assert res.freshness.trust_race_vdot
    assert res.vdot == pytest.approx(res.raw_vdot, abs=0.05)
    assert res.vdot > 33.0


def test_resolve_merge_vdot_detrains_when_marathon_window_only():
    from datetime import date

    # Only marathon anchor available — 28d break should discount.
    races = [
        {"category": "Marathon", "date": "2025-10-11", "duration_s": HMS(4, 0, 25)},
    ]
    res = rd.resolve_merge_vdot(
        races,
        _cindy_offseason_weeks(),
        marathon_date=date(2025, 10, 11),
        today=date(2026, 6, 15),
    )
    assert res is not None
    assert res.break_days == 28
    assert res.vdot < res.raw_vdot


# --- Top-level assessment (Kelly-like) -------------------------------------------
def test_assess_readiness_kelly():
    kelly = AthleteInputs(
        name="Kelly", vdot=42.6, goal_marathon_s=HMS(3, 45, 0), w_now=10.9, p_history=47.9,
        longest_run_mi=13.0, days_per_week=5, race_date="2026-10-11", block_weeks=18,
    )
    a = rd.assess_readiness(kelly, race_age_days=31, recent_sustained_mpw=21.0)
    assert a.freshness.trust_race_vdot           # 31-day-old race, no break -> trust
    assert a.current_vdot == 42.6
    assert a.reentry_start_mpw == 21.0           # uses the recent sustained high
    assert a.recommended_peak_mpw == pytest.approx(47.9, abs=0.05)
    assert a.goal.verdict == "within_current"    # her 3:45 is conservative vs VDOT 42.6
    assert "Marathon" in a.equivalent_times


# --- Volume-capacity decay (house heuristic) -------------------------------------
def test_decayed_volume_capacity_at_zero_weeks_full_peak():
    assert rd.decayed_volume_capacity(50.0, 0) == 50.0


def test_decayed_volume_capacity_floor_at_sixteen_weeks():
    assert rd.decayed_volume_capacity(50.0, 16) == 20.0  # 50 * 0.40


def test_decayed_volume_capacity_at_two_weeks():
    assert rd.decayed_volume_capacity(40.0, 2) == 36.0  # 40 * 0.90


# --- Tune-up ladder --------------------------------------------------------------
def test_tune_up_ladder_targets_sit_between_current_and_goal():
    # Gaurav-like: current 37, 3:45 goal needs VDOT ~41 (a stretch).
    lad = rd.tune_up_ladder(37.0, HMS(3, 45, 0), build_weeks=15, taper_weeks=3)
    assert lad.required_vdot == 41.0
    assert lad.verdict == "stretch"
    # Short/sharp ladder: 5K → 10K → 10K (no half marathon close to the goal; cf. Pfitzinger/Higdon).
    assert [c.label for c in lad.checkpoints] == ["5K", "10K", "10K"]
    for c in lad.checkpoints:
        # On-track-for-goal VDOT rises between current and required, so its target time is
        # faster (smaller) than the realistic/projected time at the same distance.
        assert 37.0 <= c.on_track_vdot <= 41.0
        assert c.on_track_time_s <= c.projected_time_s
    # Checkpoints are ordered earlier→later in the build.
    assert [c.week for c in lad.checkpoints] == sorted(c.week for c in lad.checkpoints)


def test_tune_up_ladder_dates_when_race_date_known():
    lad = rd.tune_up_ladder(37.0, HMS(3, 45, 0), build_weeks=15, taper_weeks=3, race_date="2026-11-01")
    for c in lad.checkpoints:
        assert c.date is not None and c.date < "2026-11-01"
    # The 5K is earliest, the race-prep 10K is closest to race day.
    assert lad.checkpoints[0].date < lad.checkpoints[-1].date


def test_tune_up_outcome_maps_verdict_to_status():
    goal = HMS(3, 5, 0)  # demands a high VDOT
    # Fitness already at/above the goal need reads on-track; far below reads behind.
    assert rd.tune_up_outcome(57.0, goal, weeks_remaining=10).status == "on_track"
    behind = rd.tune_up_outcome(34.0, goal, weeks_remaining=10)
    assert behind.status == "behind"
    assert behind.verdict == "unrealistic"
    assert behind.realistic_time_s and behind.realistic_time_s > goal  # a slower, defensible re-anchor
    assert behind.measured_vdot == 34.0
