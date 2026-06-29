"""Historical training-block capacity profile + durable store (athlete profiling, not engine)."""

from __future__ import annotations

from pathlib import Path

from engine.analyze import compute_capacity_profile
from store.db import Store
from store.models import Athlete, TrainingBlock


def _run(name: str, miles: float, day: str, *, pace: str = "9:00 /mi") -> dict:
    return {
        "sport_type": "Run",
        "name": name,
        "description": "",
        "stats": {"Distance": f"{miles:.2f} mi", "Pace": pace, "Time": "1h 0m"},
        "start_date": f"{day}T08:00:00",
    }


def _block_weeks() -> list[dict]:
    return [
        {
            "week_start": "2025-09-01",
            # Two runs on the *same* day (Mon) + a long run Sat: 2 distinct run days, 15 mi.
            "workouts": [
                _run("Morning Run", 4.0, "2025-09-01"),
                _run("Lunch shake", 1.0, "2025-09-01"),
                {"sport_type": "Workout", "name": "Pilates", "stats": {"Time": "45m"}, "start_date": "2025-09-03T18:00:00"},
                _run("Long run", 10.0, "2025-09-06"),
            ],
        },
        {
            "week_start": "2025-09-08",
            # Single run that *is* the whole week → long run is 100% of weekly miles.
            "workouts": [_run("Solo long run", 8.0, "2025-09-13")],
        },
        {
            "week_start": "2025-09-15",
            # Race week: the marathon itself, excluded from the "training" long-run stats.
            "workouts": [_run("Berlin Marathon", 26.3, "2025-09-15", pace="8:40 /mi")],
        },
    ]


def test_capacity_profile_counts_days_miles_and_long_share() -> None:
    prof = compute_capacity_profile(_block_weeks(), marathon_date="2025-09-15")

    assert prof["weeks_total"] == 3
    assert prof["weeks_with_runs"] == 3
    # distinct run-days: week1=2, week2=1, week3=1
    assert prof["max_run_days_per_week"] == 2
    assert prof["avg_run_days_per_week"] == 1.3
    assert prof["peak_weekly_miles"] == 26.3
    # longest single run overall includes the race; training-only excludes it.
    assert prof["longest_run_mi"] == 26.3
    assert prof["longest_run_excl_race_mi"] == 10.0
    # week2's lone 8-miler is 100% of its week; race week is not counted in the share stats.
    assert prof["max_long_run_pct"] == 100
    race_weeks = [w for w in prof["weeks"] if w["race_week"]]
    assert len(race_weeks) == 1 and race_weeks[0]["week_start"] == "2025-09-15"


def test_capacity_profile_empty_is_safe() -> None:
    prof = compute_capacity_profile([], marathon_date=None)
    assert prof["weeks_total"] == 0
    assert prof["peak_weekly_miles"] == 0.0
    assert prof["max_long_run_pct"] == 0


def _store(tmp_path: Path) -> Store:
    return Store(db_path=tmp_path / "s.db", project_root=tmp_path)


def _make_block(athlete_id: str, marathon_date: str, *, strava: str | None = None) -> TrainingBlock:
    prof = compute_capacity_profile(_block_weeks(), marathon_date=marathon_date)
    return TrainingBlock(
        id=Store.training_block_id(athlete_id, marathon_date),
        athlete_id=athlete_id,
        strava_athlete_id=strava,
        marathon_date=marathon_date,
        marathon_name="Berlin Marathon",
        block_start="2025-09-01",
        block_end=marathon_date,
        weeks=_block_weeks(),
        profile=prof,
    )


def test_save_and_read_training_block_round_trips(tmp_path: Path) -> None:
    s = _store(tmp_path)
    bid = s.save_training_block(_make_block("ana", "2025-09-15"))
    got = s.get_training_block(bid)
    assert got is not None
    assert got.marathon_date == "2025-09-15"
    assert len(got.weeks) == 3
    assert got.profile["longest_run_excl_race_mi"] == 10.0


def test_resave_same_marathon_is_idempotent(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.save_training_block(_make_block("ana", "2025-09-15"))
    s.save_training_block(_make_block("ana", "2025-09-15"))  # re-scrape refreshes one row
    assert len(s.list_training_blocks("ana")) == 1
    # a distinct marathon accumulates a second row, newest first
    s.save_training_block(_make_block("ana", "2026-11-01"))
    blocks = s.list_training_blocks("ana")
    assert [b.marathon_date for b in blocks] == ["2026-11-01", "2025-09-15"]
    assert s.latest_training_block("ana").marathon_date == "2026-11-01"


def test_block_is_readable_by_store_key_or_strava_id(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.upsert_athlete(Athlete(id="ana", strava_athlete_id="999", name="Ana"))
    s.save_training_block(_make_block("ana", "2025-09-15", strava="999"))
    assert len(s.list_training_blocks("ana")) == 1
    assert len(s.list_training_blocks("999")) == 1


def test_linking_athlete_adopts_pre_import_scrape(tmp_path: Path) -> None:
    # A scrape that ran before the athlete was linked keys its block by the raw Strava id.
    s = _store(tmp_path)
    s.save_training_block(_make_block("999", "2025-09-15", strava="999"))
    assert s.latest_training_block("ana") is None  # slug lookup can't see the orphan yet

    # Linking the athlete to that Strava id re-homes the orphan to the canonical slug.
    s.upsert_athlete(Athlete(id="ana", strava_athlete_id="999", name="Ana"))
    block = s.latest_training_block("ana")
    assert block is not None and block.athlete_id == "ana"
    assert block.id == "ana:2025-09-15"
    # Still reachable by Strava id, and not duplicated.
    assert len(s.list_training_blocks("999")) == 1
    assert len(s.list_training_blocks("ana")) == 1


def test_adoption_drops_orphan_when_canonical_block_exists(tmp_path: Path) -> None:
    # A canonical slug-keyed block already exists for the marathon; the stale Strava-keyed orphan
    # is dropped rather than duplicated when the athlete is (re)linked.
    s = _store(tmp_path)
    s.save_training_block(_make_block("ana", "2025-09-15", strava="999"))
    s.save_training_block(_make_block("999", "2025-09-15", strava="999"))  # orphan, same marathon
    s.upsert_athlete(Athlete(id="ana", strava_athlete_id="999", name="Ana"))
    assert len(s.list_training_blocks("ana")) == 1
