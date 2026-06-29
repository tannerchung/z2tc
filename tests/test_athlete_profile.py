"""Tests for the pure athlete-dossier builders (engine/athlete_profile.py).

Synthetic fixtures lock the responder classification, volume profile, goal realism, and anchor
staleness — the personalization signals the dossier turns history into."""

from __future__ import annotations

from datetime import date

from engine import athlete_profile as ap


def _wk(ws: str, mi: float, long_pct: float = 0.0) -> ap.WeeklyVolume:
    return ap.WeeklyVolume(week_start=ws, miles=mi, long_pct=long_pct)


def _race(d: str, cat: str, dist_m: float, vdot: float, trailing: float | None = None) -> ap.RacePerformance:
    return ap.RacePerformance(date=d, name=cat, category=cat, distance_m=dist_m, time_s=1, vdot=vdot, trailing_4wk_mpw=trailing)


def test_pearson_edges():
    assert ap._pearson([1, 2], [1, 2]) is None            # <3 points
    assert ap._pearson([1, 1, 1], [1, 2, 3]) is None       # no variance in x
    assert ap._pearson([1, 2, 3], [2, 4, 6]) == 1.0        # perfect positive


def test_percentile_interpolates():
    assert ap._percentile([10.0], 0.5) == 10.0
    assert ap._percentile([10.0, 20.0], 0.5) == 15.0
    assert ap._percentile([10.0, 20.0, 30.0], 0.25) == 15.0


def test_volume_profile_opener_and_dominance():
    # A choppy block that opens ~10 and is long-run-dominant; the opener is the median of the first
    # (up to 3) active weeks, zeros are ignored, and the long-run note fires above ~70%.
    weeks = [
        _wk("2025-06-16", 10.0, 60), _wk("2025-06-23", 9.3, 80), _wk("2025-06-30", 4.6, 100),
        _wk("2025-07-14", 0.0, 0), _wk("2025-08-18", 21.2, 90), _wk("2025-10-06", 26.9, 81),
    ]
    v = ap.build_volume_profile(weeks)
    assert v.demonstrated_opener_mpw == 9.3       # median of [10.0, 9.3, 4.6]
    assert v.peak_mpw == 26.9
    assert v.active_weeks == 5                      # the 0-mile week is excluded
    assert v.long_run_dominance_pct >= 70
    assert any("long-run-dominant" in n for n in v.notes)


def test_volume_profile_no_active_weeks():
    v = ap.build_volume_profile([_wk("2025-06-16", 0.0)])
    assert v.active_weeks == 0 and v.peak_mpw == 0.0


def test_attach_trailing_volume_window():
    feed = [_wk("2025-09-29", 20.0), _wk("2025-10-06", 24.0), _wk("2025-10-13", 18.0)]
    races = [_race("2025-10-20", "Marathon", 42195.0, 38.0)]
    ap.attach_trailing_volume(races, feed, window_days=28)
    assert races[0].trailing_4wk_mpw == 20.7        # mean(20, 24, 18) within 28d before the race


def test_responder_volume_sensitive():
    races = [
        _race("2025-01-01", "Half Marathon", 21097.5, 34.0, trailing=5.0),
        _race("2025-04-01", "Half Marathon", 21097.5, 37.0, trailing=15.0),
        _race("2025-08-01", "Half Marathon", 21097.5, 40.0, trailing=25.0),
    ]
    f = ap.build_fitness_timeline(races, current_vdot=40.0)
    assert f.volume_vdot_corr is not None and f.volume_vdot_corr >= 0.5
    assert f.responder == "volume-sensitive"


def test_responder_speed_dominant():
    races = [
        _race("2025-05-03", "5K", 5000.0, 43.0, trailing=20.0),
        _race("2025-06-14", "10K", 10000.0, 39.0, trailing=6.0),
        _race("2025-11-02", "Marathon", 42195.0, 37.0, trailing=22.0),
    ]
    f = ap.build_fitness_timeline(races, current_vdot=37.0)
    assert f.endurance_gap is not None and f.endurance_gap >= 3.0
    assert f.responder == "speed-dominant"


def test_responder_stable_when_vdot_flat():
    races = [
        _race("2025-01-01", "Half Marathon", 21097.5, 38.0, trailing=10.0),
        _race("2025-04-01", "Half Marathon", 21097.5, 38.5, trailing=20.0),
        _race("2025-08-01", "Half Marathon", 21097.5, 37.5, trailing=15.0),
    ]
    f = ap.build_fitness_timeline(races, current_vdot=38.0)
    assert (f.vdot_max - f.vdot_min) < ap._FLAT_VDOT_SPAN
    assert f.responder == "stable"


def test_responder_insufficient_data():
    races = [_race("2025-01-01", "10K", 10000.0, 39.0), _race("2025-04-01", "Half Marathon", 21097.5, 38.0)]
    assert ap.build_fitness_timeline(races, 38.0).responder == "insufficient-data"


def test_assess_goals_and_anchor():
    goals = ap.assess_goals(37.0, [("A", 3 * 3600 + 45 * 60), ("B", 3 * 3600 + 55 * 60)], build_weeks=15)
    by = {g.label: g for g in goals}
    assert by["A"].verdict in ("stretch", "unrealistic")   # 3:45 off VDOT 37 is a reach
    assert by["B"].verdict in ("in_reach", "within_current")
    assert by["A"].required_vdot > by["B"].required_vdot

    today = date(2026, 6, 26)
    assert ap.anchor_confidence(37.0, "2025-05-17", today=today).stale is True   # 405 d
    assert ap.anchor_confidence(37.0, "2026-06-01", today=today).stale is False  # 25 d
    assert ap.anchor_confidence(37.0, None, today=today).age_days is None


def test_build_dossier_recommendations_for_speed_dominant_stretch():
    weeks = [_wk("2025-06-16", 10.0, 80), _wk("2025-06-23", 9.0, 85), _wk("2025-08-18", 21.0, 90)]
    races = [
        _race("2025-05-03", "5K", 5000.0, 43.0),
        _race("2025-06-14", "10K", 10000.0, 39.0),
        _race("2025-11-02", "Marathon", 42195.0, 37.0),
    ]
    feed = [_wk("2025-05-05", 20.0), _wk("2025-06-09", 6.0), _wk("2025-10-27", 22.0)]
    d = ap.build_dossier(
        "Test", volume_weeks=weeks, races=races, feed_weeks=feed, current_vdot=37.0,
        goals=[("A", 3 * 3600 + 45 * 60), ("B", 3 * 3600 + 55 * 60)], source_date="2025-05-17",
        build_weeks=15, today=date(2026, 6, 26), injury_prone=True, current_opener_mpw=5.6,
    )
    blob = "\n".join(d.recommendations)
    assert "reentry_start_mpw" in blob and "opens at only 5.6" in blob   # opener flagged vs current plan
    assert "ramp cautiously" in blob                                     # injury-prone caveat
    assert d.fitness.responder == "speed-dominant"
    assert "Speed-dominant" in blob
    assert "stretch" in blob and "tune-up" in blob.lower()               # A-goal + stale anchor guidance

    # Step 2: the same opener signal becomes a concrete, reviewable proposed input (never applied).
    prop = next(p for p in d.proposed_inputs if p.field == "reentry_start_mpw")
    assert prop.value == round(d.volume.demonstrated_opener_mpw)
    assert prop.current == 5.6
    assert "demonstrated volume" in prop.rationale and "injury history" in prop.rationale


def test_proposed_inputs_skips_when_plan_already_matches_opener():
    # When the current plan already opens at the demonstrated volume, there is nothing to propose.
    vol = ap.VolumeProfile(
        demonstrated_opener_mpw=18.0, sustainable_low_mpw=15.0, sustainable_high_mpw=25.0,
        peak_mpw=30.0, avg_active_mpw=20.0, long_run_dominance_pct=0.0, active_weeks=8,
    )
    assert ap.proposed_inputs(vol, current_opener_mpw=18.0, injury_prone=False) == []
    # A meaningfully lower current opener does produce a proposal.
    out = ap.proposed_inputs(vol, current_opener_mpw=10.0, injury_prone=False)
    assert len(out) == 1 and out[0].field == "reentry_start_mpw" and out[0].value == 18
