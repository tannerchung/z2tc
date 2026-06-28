"""Dossier snapshot persistence (Phase 2): append-only `dossier_snapshots` accumulate the
personalization signals across runs, with the flattened query columns populated."""

from __future__ import annotations

from pathlib import Path

import main
from engine.athlete_profile import DOSSIER_VERSION
from store.db import SCHEMA_VERSION, Store
from store.models import Athlete, DossierSnapshot, SurveyInputs, TrainingBlock


def _store(tmp_path: Path) -> Store:
    return Store(db_path=tmp_path / "s.db", project_root=tmp_path)


def _survey() -> SurveyInputs:
    return SurveyInputs(
        name="Snap",
        vdot=50.0,
        goal_marathon_s=3 * 3600 + 30 * 60,
        w_now=35.0,
        p_history=40.0,
        longest_run_mi=16.0,
        days_per_week=5,
        race_date="2026-10-10",
        injury_prone=True,
    )


def _block(athlete_id: str) -> TrainingBlock:
    weeks = [
        {"week_start": ws, "total_distance": "30.0 mi"}
        for ws in ("2025-08-03", "2025-08-10", "2025-08-17", "2025-08-24")
    ]
    report = {
        "all_races_detected": [
            {"date": "2025-08-31", "name": "Half", "category": "Half",
             "distance_mi": 13.1, "duration_s": 6300}
        ],
        "recommended_vdot": {"source_race": {"date": "2025-08-31"}},
    }
    return TrainingBlock(
        id=Store.training_block_id(athlete_id, "2025-08-31"),
        athlete_id=athlete_id, strava_athlete_id="777",
        marathon_date="2025-08-31", weeks=weeks, report=report,
    )


def test_schema_version_current(tmp_path: Path) -> None:
    db = _store(tmp_path)
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_snapshot_roundtrip_and_flattened_columns(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.upsert_athlete(Athlete(id="ana", strava_athlete_id="777", name="Snap"))
    snap = DossierSnapshot(
        athlete_id="ana", dossier_version=DOSSIER_VERSION, inputs_fingerprint="fp1",
        full_json={"name": "Snap"}, responder="stable", demonstrated_opener_mpw=32.0,
        peak_mpw=55.0, sustainable_low_mpw=30.0, sustainable_high_mpw=45.0,
        volume_vdot_corr=0.2, endurance_gap=1.5, current_vdot=50.0,
        anchor_age_days=40, anchor_stale=False, injury_prone=True,
    )
    s.append_dossier_snapshot(snap)
    rows = s.list_dossier_snapshots("ana")
    assert len(rows) == 1
    r = rows[0]
    assert r["responder"] == "stable"
    assert r["demonstrated_opener_mpw"] == 32.0
    assert r["peak_mpw"] == 55.0
    assert r["anchor_stale"] == 0
    assert r["injury_prone"] == 1
    assert r["dossier_version"] == DOSSIER_VERSION


def test_snapshots_accrue_across_report_runs(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.upsert_athlete(Athlete(id="ana", strava_athlete_id="777", name="Snap"))
    s.save_survey_baseline("ana", _survey())
    s.save_training_block(_block("ana"))

    empty = tmp_path / "m"
    empty.mkdir()
    for _ in range(3):
        d = main._load_dossier(s, "ana", marathon_dir=str(empty))
        main._capture_dossier_snapshot(s, "ana", d, inputs_fingerprint="fp")

    rows = s.list_dossier_snapshots("ana")
    assert len(rows) == 3
    assert all(r["current_vdot"] is not None for r in rows)
    assert all(r["injury_prone"] == 1 for r in rows)
