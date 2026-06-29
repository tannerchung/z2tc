"""`main._load_dossier` source precedence: the durable training block in the store backs the race
history + weekly feed, so the dossier no longer depends on the output/marathon/ files surviving.
Explicit --report/--training paths still override the store."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import main
from store.db import Store
from store.events import EventRecord, TuneUpResultPayload
from store.models import Athlete, SurveyInputs, TrainingBlock
from engine.vdot import RACE_METERS, vdot_from_race


def _store(tmp_path: Path) -> Store:
    return Store(db_path=tmp_path / "s.db", project_root=tmp_path)


def _survey() -> SurveyInputs:
    return SurveyInputs(
        name="Dossier",
        vdot=50.0,
        goal_marathon_s=3 * 3600 + 30 * 60,
        w_now=35.0,
        p_history=40.0,
        longest_run_mi=16.0,
        days_per_week=5,
        race_date="2026-10-10",
    )


def _block(athlete_id: str, *, race_date: str, trailing_mpw: float) -> TrainingBlock:
    """A block whose stored report carries one detected race and whose stored weeks cover the four
    weeks before it (so trailing-volume attaches purely from the DB)."""
    weeks = [
        {"week_start": ws, "total_distance": f"{trailing_mpw:.1f} mi"}
        for ws in ("2025-08-03", "2025-08-10", "2025-08-17", "2025-08-24")
    ]
    report = {
        "all_races_detected": [
            {
                "date": race_date,
                "name": "Summer Half",
                "category": "Half",
                "distance_mi": 13.1,
                "duration_s": 6300,
            }
        ],
        "recommended_vdot": {"source_race": {"date": race_date}},
    }
    return TrainingBlock(
        id=Store.training_block_id(athlete_id, race_date),
        athlete_id=athlete_id,
        strava_athlete_id="777",
        marathon_date=race_date,
        weeks=weeks,
        report=report,
    )


def test_dossier_reads_races_and_feed_from_store_block(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.upsert_athlete(Athlete(id="ana", strava_athlete_id="777", name="Dossier"))
    s.save_survey_baseline("ana", _survey())
    s.save_training_block(_block("ana", race_date="2025-08-31", trailing_mpw=30.0))

    # Point at an empty marathon dir: there are no report_/training_ files, so the only possible
    # source is the stored training block.
    empty = tmp_path / "marathon_empty"
    empty.mkdir()
    dossier = main._load_dossier(s, "ana", marathon_dir=str(empty))

    assert dossier is not None
    assert [r.name for r in dossier.fitness.races] == ["Summer Half"]
    # trailing_4wk_mpw is only populated when the weekly feed resolved — here, from block.weeks.
    assert dossier.fitness.races[0].trailing_4wk_mpw == 30.0
    assert dossier.anchor.source_date == "2025-08-31"


def test_explicit_report_path_overrides_store_block(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.upsert_athlete(Athlete(id="ana", strava_athlete_id="777", name="Dossier"))
    s.save_survey_baseline("ana", _survey())
    s.save_training_block(_block("ana", race_date="2025-08-31", trailing_mpw=30.0))

    override = tmp_path / "report_override.json"
    override.write_text(
        json.dumps(
            {
                "all_races_detected": [
                    {
                        "date": "2025-09-20",
                        "name": "Override 10K",
                        "category": "10K",
                        "distance_mi": 6.2,
                        "duration_s": 2400,
                    }
                ],
                "recommended_vdot": {"source_race": {"date": "2025-09-20"}},
            }
        ),
        encoding="utf-8",
    )
    dossier = main._load_dossier(s, "ana", report=str(override))

    assert dossier is not None
    assert [r.name for r in dossier.fitness.races] == ["Override 10K"]
    assert dossier.anchor.source_date == "2025-09-20"


def test_tune_up_event_freshens_dossier_anchor(tmp_path: Path) -> None:
    """A recorded tune-up result surfaces in the dossier timeline and freshens the anchor, so the
    stale-anchor recommendation is suppressed once a fresh result lands (closes the flywheel)."""
    s = _store(tmp_path)
    s.upsert_athlete(Athlete(id="ana", strava_athlete_id="777", name="Dossier"))
    s.save_survey_baseline("ana", _survey())
    # Stale source: a race well past the freshness window.
    stale = (date.today() - timedelta(days=200)).isoformat()
    s.save_training_block(_block("ana", race_date=stale, trailing_mpw=30.0))

    empty = tmp_path / "marathon_empty"
    empty.mkdir()
    before = main._load_dossier(s, "ana", marathon_dir=str(empty))
    assert before is not None and before.anchor.stale is True
    assert any("stale" in r.lower() for r in before.recommendations)

    # Record a fresh tune-up: a 10K a few days ago.
    tu_date = (date.today() - timedelta(days=3)).isoformat()
    dist_m = RACE_METERS["10K"]
    measured = vdot_from_race(dist_m, 2400)
    s.append_event_record(
        EventRecord(
            athlete_id="ana", source="coach", status="applied",
            payload=TuneUpResultPayload(
                distance_m=dist_m, time_s=2400, new_vdot=measured, race_date=tu_date,
            ),
        )
    )

    after = main._load_dossier(s, "ana", marathon_dir=str(empty))
    assert after is not None
    assert after.anchor.source_date == tu_date
    assert after.anchor.stale is False
    assert any(r.category == "10K" for r in after.fitness.races)
    assert not any("anchor is stale" in r.lower() for r in after.recommendations)
