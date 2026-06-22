"""Regression / determinism tests for the plan engine.

These lock the engine's *behavior* (same inputs -> same plan) and its book-cited rules.
The "Kelly" athlete is just a worked fixture for exercising the long-run math — it is not
an authoritative golden reference (the expected numbers are the engine's own coaching
choices, which we revise deliberately, not values from a published table).
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


# --- Kelly fixture: the long-run formula is deterministic ------------------------
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


def test_long_run_18mi_distance_cap():
    # Daniels Table 14.3 caps even high-mileage long runs at "the lesser of 18 mi and 130 min".
    easy_s, _ = common.easy_pace(training_paces(55))
    lr = common.daniels_long_run(70.0, easy_s)
    assert lr.recommended_mi <= common.LONG_RUN_CAP_MI + 0.05


def test_long_run_time_window_credits_slow_runner():
    # A slow (~11:00/mi) runner on enough volume that the *time* cap binds: the z2tc
    # marathon build uses Hanson's 3 h window, not Daniels' conservative 150 min, so the
    # long run reaches ~16 mi (≈3 h) instead of being clipped to ~13.6 mi (≈2.5 h).
    easy_s = 11 * 60
    literal = common.daniels_long_run(55.0, easy_s, marathon_build=False)  # Daniels 150-min anchor
    z2tc = common.daniels_long_run(55.0, easy_s, marathon_build=True)      # 3 h window
    assert literal.recommended_mi == pytest.approx(literal.time_cap_mi, abs=0.1)   # 150-min binds
    assert z2tc.recommended_mi == pytest.approx(z2tc.window_cap_mi, abs=0.1)       # 3 h binds
    assert z2tc.recommended_mi > literal.recommended_mi                            # slower runner credited
    assert 170 <= z2tc.time_on_feet_min <= 180                                     # inside the window
    assert "hanson_long_run_window" in z2tc.citations


def test_plan_notes_carry_long_run_rationale():
    plan = build_plan(_daniels_athlete())
    assert plan.notes, "plan should carry an informational long-run rationale"
    assert any("on feet" in n for n in plan.notes)
    assert any("Hanson" in n for n in plan.notes)


def test_long_run_citations_cover_all_authors():
    from engine.plan import citations

    authors = {c.author.split()[0] for c in citations.long_run_citations()}
    assert {"Daniels", "Hanson", "Pfitzinger", "Higdon"} <= authors


def test_citation_quotes_exist_on_cited_pages():
    """Guard against fabricated/drifted citations: a distinctive phrase from each must
    actually appear on the cited page(s). Skips if the (gitignored) book index isn't built."""
    import json
    import re
    from pathlib import Path

    from engine.plan import citations

    idx = Path("output/book_index")
    files = {
        "Daniels": "Daniels-running-formula.jsonl",
        "Pfitzinger": "Advanced Marathoning - Pfitzinger, Pete.jsonl",
        "Hanson": "Hansons Marathon Method - Luke Humphrey.jsonl",
        "Higdon": "Marathon, Revised and Updated_ The Ultimat - Hal Higdon.jsonl",
    }
    # A clean, bracket-free anchor phrase per citation (verified via book_search.py).
    anchors = {
        "daniels_long_run": "150 minutes (2.5 hours), even if preparing for a marathon",
        "hanson_long_run_window": "2:00–3:00 hours is the optimal window",
        "hanson_16_cap": "16-mile long run is the longest training day for the standard Hansons program",
        "pfitz_long_run_cap": "take much more out of the body than do runs in the range of 20 to 22 miles",
        "higdon_20": "Twenty miles is the longest distance that I ask people",
    }
    if not all((idx / f).exists() for f in files.values()):
        pytest.skip("book index not built (run scripts/book_search.py build)")

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    for key, anchor in anchors.items():
        cite = citations.get(key)
        pages = {int(n) for n in re.findall(r"\d+", cite.pages)}
        text = ""
        for row in (json.loads(l) for l in (idx / files[cite.author.split()[0]]).read_text().splitlines() if l.strip()):
            if row["page"] in pages:
                text += " " + row["text"]
        assert norm(anchor) in norm(text), f"{key}: anchor not found on p.{cite.pages}"


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


# --- sec.3 Volume progression invariants (Daniels p.219 hold-then-step) -----------
def test_volume_progression():
    days = 5
    vols = common.weekly_volumes(30.0, 55.0, 18, days, taper_weeks=3, hold_weeks=3, down_week_every=4)
    assert len(vols) == 18
    assert max(vols) <= 55.0 + 0.05  # never exceeds P

    build = vols[:-3]
    # Daniels p.219: hold ~3-4 wk, then step up by at most `min(days, 10)` mpw.
    holds = [v for i, v in enumerate(build) if (i + 1) % 4 != 0]
    for a, b in zip(holds, holds[1:]):
        assert b - a <= days + 0.05
    # The level is genuinely held for 3 running weeks before the first step up.
    assert build[0] == build[1] == build[2] == pytest.approx(30.0, abs=0.05)
    assert build[4] > build[2]  # week 5 (after a recovery week) steps up
    # Every 4th week is a recovery week (~80% of the held level), below its predecessor.
    for i, v in enumerate(build):
        if (i + 1) % 4 == 0:
            assert v < build[i - 1]

    taper = vols[-3:]
    assert all(t < 55.0 for t in taper)
    assert taper[0] > taper[1] > taper[2]  # strictly descending


def test_volume_already_based_reaches_peak():
    # An athlete who starts at/near peak just holds at peak with recovery weeks.
    vols = common.weekly_volumes(55.0, 55.0, 18, 6, taper_weeks=3)
    assert max(vols[:-3]) == pytest.approx(55.0, abs=0.05)


def test_comeback_ramp_reaches_demonstrated_peak():
    # Daniels ch.15 (p.284): regaining demonstrated fitness is faster than new territory.
    # A returner re-entering at half of her demonstrated peak should climb back to it; the slow
    # p.219 hold only applies ABOVE demonstrated capacity.
    days, demonstrated = 4, 38.9
    comeback = common.weekly_volumes(19.4, demonstrated, 18, days, comeback_peak=demonstrated)
    slow = common.weekly_volumes(19.4, demonstrated, 18, days)  # no comeback -> p.219 only
    assert max(comeback[:-3]) == pytest.approx(demonstrated, abs=0.05), "comeback regains P"
    assert max(slow[:-3]) < demonstrated - 1, "the slow new-territory rule alone falls short"

    # New ground beyond demonstrated capacity slows down again (Daniels p.219 / Pfitz p.50).
    beyond = common.weekly_volumes(19.4, 46.0, 18, days, comeback_peak=demonstrated)
    above = [v for v in beyond[:-3] if v > demonstrated + 0.05]
    for a, b in zip(above, above[1:]):
        assert b - a <= days + 0.05  # never jumps more than one safe step in new territory


def test_volume_step_ups_flags_increases_only():
    vols = [30, 30, 30, 24, 35, 35, 35, 28, 40]
    ups = common.volume_step_ups(vols)
    assert ups == [False, False, False, False, True, False, False, False, True]


# --- sec.5 Session caps (Daniels fig. 4.1, p.62) ---------------------------------
def test_session_caps():
    # M is 20% of the week (p.62/p.65), not 30%: 0.20 * 31 = 6.2.
    c31 = common.session_caps(31)
    assert c31 == {"T": 3.1, "M": 6.2, "I": 2.5, "R": 1.6}
    c55 = common.session_caps(55)
    assert c55 == {"T": 5.5, "M": 11.0, "I": 4.4, "R": 2.8}


def test_marathon_pace_cap_110_min():
    # At 70 mpw, 20% = 14 mi, but a slow MP makes the 110-min ceiling bind first.
    mp_s = 600  # 10:00/mi -> 110 min = 11.0 mi
    caps = common.session_caps(70, mp_s)
    assert caps["M"] == pytest.approx(11.0, abs=0.05)
    # A fast MP lets the 18-mi / 20% rule bind instead.
    assert common.session_caps(70, 360)["M"] == pytest.approx(14.0, abs=0.05)


def test_threshold_tempo_vs_cruise():
    # T volume that fits in ~20 min -> single steady tempo (Daniels p.67).
    w = common.threshold_workout(3.0, 360, "6:00")  # 3 mi @ 6:00 = 18 min
    assert w.segments[0].reps == 1 and "Tempo" in w.label
    # More T volume -> cruise intervals, not a longer continuous tempo.
    w2 = common.threshold_workout(6.0, 360, "6:00")  # 6 mi @ 6:00 = 36 min
    assert w2.segments[0].reps >= 2 and "Cruise" in w2.label
    # wu/cd (~3 mi) sits on top of the capped T work in both cases.
    assert w.distance_mi == pytest.approx(6.0, abs=0.05)


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
    assert race_days == ["Sun"]
    # Every week has a long run and a midweek medium-long run.
    for w in plan.weeks[:-1]:
        assert w.long_run is not None, f"week {w.index} has no long run"


def test_daniels_q1_is_nonstop_blend():
    # Marathon-specific Q1 is a single nonstop E/M/T session (Daniels Table 14.3), not a split.
    plan = build_plan(_daniels_athlete())
    q1s = [
        d for w in plan.weeks if w.phase in ("Threshold", "Race Prep") and not w.is_down_week
        for d in w.days if d.workout.kind == WorkoutKind.MARATHON_PACE
    ]
    assert q1s, "expected at least one Q1 marathon-pace long run"
    q1 = q1s[0].workout
    labels = [s.pace_label for s in q1.segments]
    assert "M" in labels and labels[0] == "E" and labels[-1] == "E"  # E warm-up ... E cool-down
    # MP volume in the session respects the M cap (18 mi / 20% / 110 min).
    m_mi = sum((s.distance_m or 0) for s in q1.segments if s.pace_label == "M") / common.METERS_PER_MILE
    assert m_mi <= 18.0 + 0.1


def test_higdon_builds_long_run_to_peak_by_distance():
    # Higdon's defining feature: the long run climbs by *distance* to a ~20-mi peak,
    # regardless of weekly volume, with stepback weeks and no slow base ramp.
    a = _daniels_athlete(method=common.HIGDON, longest_run_mi=20.0)
    plan = build_plan(a)
    assert plan.method == common.HIGDON
    long_runs = [
        d.workout.distance_mi
        for w in plan.weeks if w.phase != "Taper"
        for d in w.days if d.workout.kind.name in ("LONG", "MARATHON_PACE")
    ]
    assert max(long_runs) >= 18.0, "Higdon should build the long run toward ~20 mi"
    assert any(w.phase == "Stepback" for w in plan.weeks)


def test_higdon_is_pure_no_time_window_bias():
    # Pure Higdon caps the long run by DISTANCE only (p.28): even a slow runner keeps the
    # 20-mi peak, and the engine does NOT apply z2tc's Hanson time-on-feet window.
    a = _daniels_athlete(vdot=36, method=common.HIGDON, longest_run_mi=20.0)
    plan = build_plan(a)
    long_runs = [
        d.workout.distance_mi
        for w in plan.weeks if w.phase != "Taper"
        for d in w.days if d.workout.kind.name == "LONG"
    ]
    assert max(long_runs) >= 18.0, "slow runner still builds to the 20-mi distance peak"
    assert not any("window" in f.lower() for f in plan.flags), "pure Higdon has no z2tc time-window flag"
    # Novice is all-easy: no marathon-pace / speed sessions injected.
    assert not any(
        d.workout.kind.name in ("MARATHON_PACE", "INTERVAL", "THRESHOLD")
        for w in plan.weeks for d in w.days
    )


def test_pfitzinger_honors_tiers_and_flags_entry_gap():
    # Pfitzinger plans are tiered: peak comes from the tier (not p_history), starts at the
    # tier's ~33-mi week, and a below-base / uncharted-peak athlete is flagged, not capped to
    # p_history.
    from engine.plan.pfitzinger import select_tier

    assert select_tier(38.9)[0] == 55.0   # below 55 -> ch.8
    assert select_tier(60.0)[0] == 70.0   # 60 -> ch.9
    a = _pfitz_athlete(w_now=13.8, p_history=38.9, days_per_week=4, method=common.PFITZINGER)
    plan = build_plan(a)
    assert plan.peak_miles == pytest.approx(55.0, abs=0.05), "peaks at the tier, not p_history"
    assert plan.weeks[0].target_miles == pytest.approx(33.0, abs=0.05), "starts at the tier week 1"
    assert any("below entry base" in f for f in plan.flags)
    assert any("uncharted peak" in f for f in plan.flags)


def test_pfitzinger_long_run_is_a_ladder_not_a_16_floor():
    # p.257's "16 mi = a long run" is a definition, not a floor. Build-phase long runs ramp by
    # distance (his lowest schedule opens ~12 mi, p.285) toward ~20 — they are NOT clamped to 16.
    a = _pfitz_athlete(w_now=30.0, p_history=42.0, method=common.PFITZINGER)
    plan = build_plan(a)
    build_longs = [
        w.long_run.workout.distance_mi
        for w in plan.weeks
        if w.phase != "Taper" and not w.is_down_week and w.long_run is not None
    ]
    assert max(build_longs) >= 18.0, "should build toward 20-22 mi"
    assert min(build_longs) < 16.0, "early long runs are below 16 — no artificial floor"


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


def test_emit_peak_scenarios_daniels_siblings():
    a = _daniels_athlete(emit_peak_scenarios=True)
    plan = build_plan(a)
    assert plan.scenario is not None
    assert plan.scenario.scenario_id == "primary"
    assert len(plan.sibling_scenarios) == 2
    assert all(s.scenario is not None for s in plan.sibling_scenarios)


def test_hanson_plan_smoke():
    a = _daniels_athlete(method=common.HANSON, hanson_program="just_finish", days_per_week=6)
    plan = build_plan(a)
    assert plan.method == common.HANSON
    assert len(plan.weeks) == 18


def test_recommend_coaches_orders_daniels_first_for_four_days():
    from engine.plan.recommend import recommend_coaches

    a = _daniels_athlete(days_per_week=4)
    rec = recommend_coaches(a)
    assert rec[0].method == common.DANIELS


def test_coach_floor_raises_comeback_peak():
    from dataclasses import replace

    from engine.plan.intake import resolve_intake_defaults
    from engine.plan.models import AthleteInputs
    from engine.readiness import recommended_reentry_volume

    a = AthleteInputs(
        name="C",
        vdot=43,
        goal_marathon_s=3 * 3600 + 50 * 60,
        w_now=13.8,
        p_history=38.9,
        longest_run_mi=13.0,
        days_per_week=4,
        race_date="2026-10-10",
        block_weeks=18,
        coach_floor_mpw=45.0,
    )
    a = resolve_intake_defaults(replace(a, reentry_start_mpw=None))
    start, _ = recommended_reentry_volume(
        a.w_now,
        a.p_history,
        recent_sustained_mpw=a.recent_sustained_mpw,
        race_fit=a.race_fit,
        injury_prone=a.injury_prone,
        days_per_week=a.days_per_week,
    )
    a = replace(a, reentry_start_mpw=start)
    fast = common.weekly_volumes(19.4, 50.0, 18, 4, comeback_peak=common.comeback_peak_mpw(a))
    assert max(fast[:-3]) >= 45.0 - 0.1


def test_verbatim_grids_reproduction():
    # Test Higdon Novice 2 verbatim reproduction
    a_higdon = _daniels_athlete(method=common.HIGDON, higdon_program="novice2", days_per_week=4)
    plan_higdon = build_plan(a_higdon)
    assert plan_higdon.method == common.HIGDON
    assert len(plan_higdon.weeks) == 18
    # Week 8 Sunday should be Half marathon
    assert plan_higdon.weeks[7].days[6].workout.kind == WorkoutKind.RACE
    assert "Half marathon" in plan_higdon.weeks[7].days[6].workout.label
    # Week 9 Sunday should be Cross training
    assert plan_higdon.weeks[8].days[6].workout.kind == WorkoutKind.CROSS

    # Test Pfitzinger up-to-55 verbatim reproduction
    a_pfitz = _pfitz_athlete()
    plan_pfitz = build_plan(a_pfitz)
    assert plan_pfitz.method == common.PFITZINGER
    assert len(plan_pfitz.weeks) == 18
    # Week 12 Saturday should be tune-up race
    assert plan_pfitz.weeks[11].days[5].workout.kind == WorkoutKind.RACE
    assert "tune_up_race" in plan_pfitz.weeks[11].days[5].workout.flags
    # Week 18 Wednesday should be dress rehearsal
    assert "dress_rehearsal" in plan_pfitz.weeks[17].days[2].workout.flags

    # Test Hanson Beginner verbatim reproduction
    a_hanson = _daniels_athlete(method=common.HANSON, hanson_program="beginner", days_per_week=6)
    plan_hanson = build_plan(a_hanson)
    assert plan_hanson.method == common.HANSON
    assert len(plan_hanson.weeks) == 18
    # Week 6 Tuesday should be SPEED: 12 × 400 / 400 recovery
    tue_w = plan_hanson.weeks[5].days[1].workout
    assert tue_w.kind == WorkoutKind.INTERVAL
    assert "SPEED" in tue_w.label
    assert len(tue_w.segments) == 1
    assert tue_w.segments[0].reps == 12
    assert tue_w.segments[0].distance_m == 400.0

