"""The Zone 2 Track Club engine layers house policy over the pure plan engine."""

from __future__ import annotations

import dataclasses

from engine.plan import apply_club_policy, build_club_plan, build_plan, common
from engine.plan.models import AthleteInputs


def _athlete(**over) -> AthleteInputs:
    # A Daniels-method athlete (the engine the club policy modifies): a 4-day, lower-mileage load.
    base = dict(
        name="Pat", vdot=43, goal_marathon_s=3 * 3600 + 55 * 60, w_now=28.0, p_history=31.0,
        longest_run_mi=13.0, days_per_week=4, race_date="2026-10-10", block_weeks=18,
        method=common.DANIELS,
    )
    base.update(over)
    return AthleteInputs(**base)


def _base_weekday_quality_counts(plan) -> list[int]:
    counts = []
    for w in plan.weeks:
        if w.phase == "Base" and not w.is_down_week:
            counts.append(sum(1 for d in w.days if d.day != "Sat" and d.workout.is_quality))
    return counts


def test_club_policy_defaults_two_quality_and_base_ramp():
    resolved = apply_club_policy(_athlete())
    assert resolved.weekday_quality_sessions == 2
    assert resolved.base_quality_ramp is True
    assert resolved.long_run_share_cap == 0.50


def test_club_policy_respects_explicit_opt_down():
    # A coach who sets a single midweek quality keeps it, and the Base ramp stays off.
    resolved = apply_club_policy(_athlete(weekday_quality_sessions=1))
    assert resolved.weekday_quality_sessions == 1
    assert resolved.base_quality_ramp is False


def test_club_policy_preserves_explicit_coach_overrides():
    # Tri-state precedence: an explicit coach choice always survives the club resolver, even when it
    # equals "off" (base_quality_ramp=False) or differs from the club default (share cap).
    resolved = apply_club_policy(
        _athlete(base_quality_ramp=False, long_run_share_cap=0.33, weekday_quality_sessions=2)
    )
    assert resolved.base_quality_ramp is False
    assert resolved.long_run_share_cap == 0.33


def test_club_policy_is_idempotent():
    once = apply_club_policy(_athlete())
    twice = apply_club_policy(once)
    assert once == twice


def _stretch_athlete(**over) -> AthleteInputs:
    # A goal that needs fitness the athlete hasn't shown (low VDOT, fast goal) -> the club schedules a
    # tune-up ladder to verify it mid-block.
    base = dict(
        name="Reach", vdot=46.0, goal_marathon_s=3 * 3600 + 5 * 60, w_now=30.0, p_history=40.0,
        longest_run_mi=14.0, days_per_week=5, race_date="2026-11-01", block_weeks=18,
        method=common.DANIELS,
    )
    base.update(over)
    return AthleteInputs(**base)


def test_club_default_aggressive_ramp_off_and_overridable():
    from engine.plan.club import ClubPolicy, apply_club_policy as acp

    # Club default is the textbook 3-week hold (ramp off); flipping the policy turns it on club-wide;
    # an explicit coach choice (even "off") always survives the resolver.
    assert apply_club_policy(_stretch_athlete()).aggressive_volume_ramp is False
    assert acp(_stretch_athlete(), ClubPolicy(allow_aggressive_ramp=True)).aggressive_volume_ramp is True
    assert apply_club_policy(_stretch_athlete(aggressive_volume_ramp=False)).aggressive_volume_ramp is False
    assert apply_club_policy(_stretch_athlete(aggressive_volume_ramp=True)).aggressive_volume_ramp is True


def test_club_schedules_tune_up_ladder_for_stretch_goal():
    resolved = apply_club_policy(_stretch_athlete())
    labels = [t.label for t in resolved.tune_up_races]
    assert labels == ["5K", "10K", "10K"]
    # Each lands on a real build week (never a down week or the final build week) with an advisory time.
    weeks = [t.week for t in resolved.tune_up_races]
    assert weeks == sorted(set(weeks))
    assert all(w % 4 != 0 for w in weeks)
    assert all(t.target_time_s for t in resolved.tune_up_races)


def test_daniels_gets_tune_ups_even_when_goal_in_reach():
    # Club default: a Daniels plan always gets the empirical 5K/10K ladder — even an in-reach goal —
    # because the mid-block race is how we refine the athlete's VDOT and paces.
    resolved = apply_club_policy(_athlete())  # _athlete() is Daniels with a comfortable 3:55 goal
    assert [t.label for t in resolved.tune_up_races] == ["5K", "10K", "10K"]


def test_non_daniels_skips_tune_ups_when_goal_in_reach():
    # For non-Daniels methods, an in-reach goal has nothing to verify -> no club ladder scheduled.
    resolved = apply_club_policy(_athlete(method=common.HANSON))
    assert resolved.tune_up_races == ()


def test_coach_can_opt_out_of_tune_ups():
    # An explicit empty tuple is a coach choice ("no tune-ups") and survives the club resolver.
    resolved = apply_club_policy(_stretch_athlete(tune_up_races=()))
    assert resolved.tune_up_races == ()


def test_tune_up_races_land_in_plan_on_cutback_weeks():
    plan = build_club_plan(_stretch_athlete())
    tune_up_weeks = {
        w.index: w
        for w in plan.weeks
        if any(d.workout.kind.name == "RACE" and (d.workout.distance_mi or 0) < 26.0 for d in w.days)
    }
    assert len(tune_up_weeks) == 3
    by_index = {w.index: w for w in plan.weeks}
    for idx, w in tune_up_weeks.items():
        # The race replaces the long run and the week is a mini-cutback (lighter than the neighbor
        # build week before it), and it carries no extra midweek quality (the race is the quality).
        race_days = [d for d in w.days if d.workout.kind.name == "RACE"]
        assert len(race_days) == 1
        assert race_days[0].day == "Sat"
        prev = by_index.get(idx - 1)
        if prev is not None and not prev.is_down_week:
            assert w.target_miles < prev.target_miles
        assert len(w.quality_days) == 1


def test_club_tune_up_scheduling_is_idempotent():
    once = apply_club_policy(_stretch_athlete())
    twice = apply_club_policy(once)
    assert once == twice


def _race_weeks(plan):
    return [
        w for w in plan.weeks
        if any(d.workout.kind.name == "RACE" and 0 < (d.workout.distance_mi or 0) < 26.0 for d in w.days)
    ]


def test_tune_ups_are_method_agnostic():
    # Placement is a club post-process, not Daniels-only: a Hanson plan (no native tune-ups) still
    # gets the club's short/sharp 5K → 10K → 10K ladder seated into the build (no late half).
    plan = build_club_plan(_stretch_athlete(method=common.HANSON))
    race_weeks = _race_weeks(plan)
    labels = {
        d.workout.label
        for w in race_weeks
        for d in w.days
        if d.workout.kind.name == "RACE"
    }
    assert labels == {"5K tune-up race", "10K tune-up race"}
    assert len(race_weeks) == 3  # 5K + two 10K checkpoints
    assert not any(
        "Half" in d.workout.label for w in race_weeks for d in w.days
    ), "no half marathon should be scheduled close to the goal"


def test_club_defers_to_native_method_tune_ups_with_targets():
    # Pfitzinger/Higdon prescribe their own mid-block tune-up races; the club must not stack a second
    # ladder on top — it defers (with a flag), leaves the native races in place, but annotates them
    # with the same goal-linked target times so those athletes also know what to aim for.
    plan = build_club_plan(_stretch_athlete(method=common.PFITZINGER))
    assert any("tune-up ladder deferred" in f for f in plan.flags)
    club_labels = {"5K tune-up race", "10K tune-up race", "Half Marathon tune-up race"}
    assert not any(
        d.workout.label in club_labels for w in plan.weeks for d in w.days
    ), "club ladder should not be added when the method already races mid-block"
    native = _race_weeks(plan)
    assert native, "Pfitzinger should keep its native tune-up races"
    assert all(
        any("tune-up target" in f for f in w.flags) for w in native
    ), "each native tune-up week should carry a goal-linked target"


def test_pure_engine_keeps_base_aerobic():
    # Without the club layer, the pure engine is textbook Daniels: a single midweek quality and an
    # aerobic Base (no weekday quality before the Threshold phase).
    plan = build_plan(_athlete())
    assert all(c == 0 for c in _base_weekday_quality_counts(plan))
    for w in plan.weeks:
        if w.phase in ("Threshold", "Race Prep") and not w.is_down_week:
            assert len(w.quality_days) == 2, f"week {w.index}"


def test_club_engine_eases_two_quality_into_base():
    # The club engine adds the second quality and ramps it into Base: one effort early, two by the
    # back half of the phase, then two every non-down build week after. (Tune-ups opted out so a
    # race week — whose only quality is the race — doesn't perturb the weekday-quality ramp count.)
    plan = build_club_plan(_athlete(tune_up_races=()))
    base_counts = _base_weekday_quality_counts(plan)
    assert base_counts, "expected base build weeks"
    assert base_counts[0] == 1, base_counts
    assert base_counts[-1] == 2, base_counts
    assert base_counts == sorted(base_counts), base_counts

    for w in plan.weeks:
        if w.phase in ("Threshold", "Race Prep") and not w.is_down_week:
            assert len(w.quality_days) == 2, f"week {w.index}"


def test_long_run_share_cap_raises_long_run_for_low_mileage():
    # Textbook caps the long run near a third of the week; the club's 0.50 share lets a low-mileage
    # athlete reach a real long run (still bounded by the time-on-feet / 18-mi ceilings).
    easy_s = 600  # 10:00/mi
    textbook = common.daniels_long_run(30, easy_s)                  # ~max(0.30*30, 30/3) = 10 mi
    raised = common.daniels_long_run(30, easy_s, share_cap=0.50)    # 0.50*30 = 15 mi
    assert raised.recommended_mi > textbook.recommended_mi
    assert raised.recommended_mi <= common.LONG_RUN_CAP_MI


def test_club_engine_matches_pure_engine_with_explicit_flags():
    # build_club_plan is just the pure engine with club defaults resolved up front (tune-ups opted
    # out so placement stays a no-op and we compare the quality/ramp/share resolution alone).
    athlete = _athlete(tune_up_races=())
    club = build_club_plan(athlete)
    explicit = build_plan(
        dataclasses.replace(
            athlete, weekday_quality_sessions=2, base_quality_ramp=True, long_run_share_cap=0.50
        )
    )
    assert [d.workout.label for w in club.weeks for d in w.days] == [
        d.workout.label for w in explicit.weeks for d in w.days
    ]


def _marathon_dates(plan) -> list[tuple[int, str]]:
    out = []
    for w in plan.weeks:
        for d in w.days:
            if d.workout.kind.name == "RACE" and (d.workout.distance_mi or 0) >= 26:
                out.append((w.index, d.workout.label))
    return out


def test_marathon_double_primary_first_appends_bridge():
    # Goal race first (Chicago 10-11), second marathon 3 wks later (NYC 11-01): the 18-wk build to the
    # goal race is followed by a 3-week recovery→bridge→race extension ending on the second race.
    from engine.plan.models import MarathonRace

    plan = build_club_plan(
        _athlete(
            race_name="Chicago", race_date="2026-10-11", block_weeks=18, tune_up_races=(),
            secondary_races=(MarathonRace("New York City", "2026-11-01"),),
        )
    )
    assert plan.block_weeks == 21 and len(plan.weeks) == 21
    races = _marathon_dates(plan)
    assert any(i == 18 and "Chicago" in lbl for i, lbl in races)
    assert races[-1] == (21, "New York City - race day")
    # Goal/paces stay anchored to the primary; the calendar anchors on the later race.
    assert plan.goal["name"] == "Chicago" and plan.goal["date"] == "2026-10-11"
    assert plan.goal["final_race_date"] == "2026-11-01"
    assert any("marathon double" in f for f in plan.flags)


def test_marathon_double_primary_later_builds_to_earlier_race():
    # Goal race (Chicago 10-11) but a marathon 2 wks earlier (Berlin 09-27): build/peak to the earlier
    # race, bridge to the goal race; the block still ends on the goal race and stays the same length.
    from engine.plan.models import MarathonRace

    plan = build_club_plan(
        _athlete(
            race_name="Chicago", race_date="2026-10-11", block_weeks=18, tune_up_races=(),
            secondary_races=(MarathonRace("Berlin", "2026-09-27"),),
        )
    )
    assert plan.block_weeks == 18
    races = _marathon_dates(plan)
    assert races[0][1].startswith("Berlin") and races[-1][1].startswith("Chicago")
    assert plan.goal["name"] == "Chicago" and plan.goal["final_race_date"] == "2026-10-11"
