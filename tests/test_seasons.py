"""Season scoping, carry-forward seeding, and resolved-inputs snapshots."""

from __future__ import annotations

from pathlib import Path

from engine.plan import ENGINE_VERSION, build_plan
from engine.plan.replan import resolve_inputs
from store.carryforward import build_next_season_survey
from store.db import Store, fingerprint_athlete_inputs
from store.events import EventRecord, ManualOverridePayload, TuneUpResultPayload
from store.models import Athlete, Season, SurveyInputs


def _survey(**kw) -> SurveyInputs:
    d = dict(
        name="Ana",
        vdot=43.0,
        goal_marathon_s=3 * 3600 + 40 * 60,
        w_now=28.0,
        p_history=35.0,
        longest_run_mi=16.0,
        days_per_week=5,
        race_date="2026-10-10",
        race_name="Fall Marathon",
        block_weeks=18,
    )
    d.update(kw)
    return SurveyInputs(**d)


def _store(tmp_path: Path) -> Store:
    return Store(db_path=tmp_path / "s.db", project_root=tmp_path)


def test_survey_override_fields_round_trip_to_athlete_inputs() -> None:
    s = _survey(
        weekday_quality_sessions=2,
        aggressive_volume_ramp=True,
        long_run_cap_mi=18.0,
        strides_per_phase=2,
        quality_long_runs_race_prep_only=True,
        reentry_start_mpw=22.0,
    )
    inp = s.to_athlete_inputs()
    assert inp.weekday_quality_sessions == 2
    assert inp.aggressive_volume_ramp is True
    assert inp.long_run_cap_mi == 18.0
    assert inp.strides_per_phase == 2
    assert inp.quality_long_runs_race_prep_only is True
    assert inp.reentry_start_mpw == 22.0


def test_record_tune_up_logs_result_and_replan_folds_vdot(tmp_path: Path) -> None:
    import argparse
    import json

    import main
    from engine.plan.replan import replan
    from engine.vdot import RACE_METERS, vdot_from_race

    db = _store(tmp_path)
    db.upsert_athlete(Athlete(id="r", name="Reach"))
    db.save_survey_baseline("r", _survey(name="Reach", vdot=46.0, race_date="2026-12-01"))

    args = argparse.Namespace(athlete_id="r", distance="10k", time=2490, json=True, db=str(tmp_path / "s.db"))
    assert main._cmd_record_tune_up(args) == 0

    measured = vdot_from_race(RACE_METERS["10K"], 2490)
    tune_ups = [json.loads(e["payload_json"]) for e in db.list_events("r") if e["event_type"] == "TuneUpResult"]
    assert len(tune_ups) == 1
    assert tune_ups[0]["new_vdot"] == measured
    assert tune_ups[0]["distance_m"] == RACE_METERS["10K"]

    # The recorded result folds into the athlete's VDOT on the next replan.
    plan = replan(_survey(name="Reach", vdot=46.0, race_date="2026-12-01").to_athlete_inputs(), db, "r")
    assert plan.vdot == measured


def test_resolved_tune_up_races_round_trip_through_store_dict() -> None:
    # The club-resolved tune-up ladder is part of the resolved AthleteInputs snapshot stored with a
    # plan; it must survive the JSON dict round-trip used by the store (plan_artifacts.resolved_inputs).
    from dataclasses import replace

    from engine.plan.models import AthleteInputs, TuneUpRace
    from store.serialization import athlete_inputs_from_dict, athlete_inputs_to_dict

    inp = AthleteInputs(
        name="Reach", vdot=46.0, goal_marathon_s=3 * 3600 + 5 * 60, w_now=30.0, p_history=40.0,
        longest_run_mi=14.0, days_per_week=5, race_date="2026-11-01", block_weeks=18,
        tune_up_races=(
            TuneUpRace(week=3, distance_m=5000.0, label="5K", target_time_s=1245),
            TuneUpRace(week=7, distance_m=10000.0, label="10K", target_time_s=2514),
        ),
    )
    back = athlete_inputs_from_dict(athlete_inputs_to_dict(inp))
    assert back.tune_up_races == inp.tune_up_races
    # None (unset) stays None rather than collapsing to an empty tuple.
    assert athlete_inputs_from_dict(athlete_inputs_to_dict(replace(inp, tune_up_races=None))).tune_up_races is None


def test_default_season_created_on_first_write(tmp_path: Path) -> None:
    db = _store(tmp_path)
    db.upsert_athlete(Athlete(id="a1", name="Ana"))
    db.save_survey_baseline("a1", _survey())
    seasons = db.list_seasons("a1")
    assert len(seasons) == 1
    assert seasons[0].status == "active"
    assert db.load_survey_baseline("a1") is not None


def test_events_and_baselines_are_season_scoped(tmp_path: Path) -> None:
    db = _store(tmp_path)
    db.upsert_athlete(Athlete(id="a1", name="Ana"))
    db.save_survey_baseline("a1", _survey(vdot=43.0))
    s1 = db.get_active_season("a1")
    assert s1 is not None
    db.append_event_record(
        EventRecord(
            athlete_id="a1", source="coach", status="applied",
            payload=TuneUpResultPayload(distance_m=5000, time_s=1200, new_vdot=50.0),
        )
    )
    assert len(db.list_events("a1")) == 1

    # A second season starts a clean log + baseline; the first stays intact.
    s2_id = db.create_season(Season(athlete_id="a1", label="Spring", race_date="2027-04-19"))
    db.save_survey_baseline("a1", _survey(vdot=45.0, race_name="Spring"), season_id=s2_id)
    assert db.list_events("a1") == []  # active season (s2) has no events
    assert len(db.list_events("a1", season_id=s1.id)) == 1  # old season keeps its log
    assert db.load_survey_baseline("a1").vdot == 45.0  # active baseline
    assert db.load_survey_baseline("a1", season_id=s1.id).vdot == 43.0


def test_set_active_season_switches_target(tmp_path: Path) -> None:
    db = _store(tmp_path)
    db.upsert_athlete(Athlete(id="a1", name="Ana"))
    db.save_survey_baseline("a1", _survey(vdot=43.0))
    s1 = db.get_active_season("a1")
    s2_id = db.create_season(Season(athlete_id="a1", label="Spring"))
    assert db.get_active_season("a1").id == s2_id
    db.set_active_season(s1.id)
    assert db.get_active_season("a1").id == s1.id
    assert db.get_season(s2_id).status == "archived"


def test_plan_artifact_stores_resolved_inputs(tmp_path: Path) -> None:
    db = _store(tmp_path)
    db.upsert_athlete(Athlete(id="a1", name="Ana"))
    s = _survey()
    db.save_survey_baseline("a1", s)
    db.append_event_record(
        EventRecord(
            athlete_id="a1", source="coach", status="applied",
            payload=ManualOverridePayload(field="weekday_quality_sessions", value=2),
        )
    )
    baseline = s.to_athlete_inputs()
    resolved = resolve_inputs(baseline, db, "a1")
    plan = build_plan(resolved)
    db.save_plan_artifact("a1", plan, fingerprint_athlete_inputs(resolved), resolved_inputs=resolved)
    art = db.load_latest_plan("a1")
    assert art is not None
    assert art.resolved_inputs is not None
    assert art.resolved_inputs["weekday_quality_sessions"] == 2
    assert art.engine_version == ENGINE_VERSION


def test_legacy_db_missing_engine_version_is_migrated(tmp_path: Path) -> None:
    import sqlite3

    db_path = tmp_path / "legacy.db"
    # Pre-versioning tables: plan_artifacts (no engine_version) + narrative_renders (no
    # plan_artifact_id), each with one legacy row.
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE plan_artifacts (
            id TEXT PRIMARY KEY, season_id TEXT, athlete_id TEXT NOT NULL,
            created_at TEXT NOT NULL, inputs_hash TEXT NOT NULL, plan_json TEXT NOT NULL,
            resolved_inputs_json TEXT
        );
        INSERT INTO plan_artifacts (id, season_id, athlete_id, created_at, inputs_hash, plan_json)
        VALUES ('legacy', NULL, 'a1', '2025-01-01', 'h', '{}');
        CREATE TABLE narrative_renders (
            id TEXT PRIMARY KEY, season_id TEXT, athlete_id TEXT NOT NULL, created_at TEXT NOT NULL,
            surface TEXT NOT NULL, template_version TEXT NOT NULL, prompt_version TEXT, llm_model TEXT,
            source TEXT NOT NULL, deterministic_text TEXT NOT NULL, final_text TEXT NOT NULL,
            changed INTEGER NOT NULL DEFAULT 0, char_delta INTEGER NOT NULL DEFAULT 0,
            guard_passed INTEGER NOT NULL DEFAULT 1, signals_json TEXT NOT NULL DEFAULT '{}',
            inputs_fingerprint TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO narrative_renders
            (id, season_id, athlete_id, created_at, surface, template_version, source,
             deterministic_text, final_text)
        VALUES ('nr', NULL, 'a1', '2025-01-01', 'summary', '1', 'deterministic', 'x', 'x');
        """
    )
    conn.commit()
    conn.close()

    # Opening the store migrates both tables and creates publications; legacy rows read back with
    # the new columns NULL.
    db = Store(db_path=db_path, project_root=tmp_path)
    art_cols = {r["name"] for r in db._conn.execute("PRAGMA table_info(plan_artifacts)")}
    assert "engine_version" in art_cols
    assert db._conn.execute(
        "SELECT engine_version FROM plan_artifacts WHERE id='legacy'"
    ).fetchone()["engine_version"] is None

    narr_cols = {r["name"] for r in db._conn.execute("PRAGMA table_info(narrative_renders)")}
    assert "plan_artifact_id" in narr_cols
    assert db._conn.execute(
        "SELECT plan_artifact_id FROM narrative_renders WHERE id='nr'"
    ).fetchone()["plan_artifact_id"] is None

    # publications is a new table → created fresh, queryable, empty.
    assert db.list_publications("a1") == []


def test_carry_forward_seeds_from_prior_ending_state(tmp_path: Path) -> None:
    prior_survey = _survey(vdot=43.0, p_history=35.0)
    resolved = prior_survey.to_athlete_inputs()
    prior_plan = build_plan(resolved)

    new_survey, prov = build_next_season_survey(
        prior_survey,
        resolved,
        prior_plan,
        label="2027 Boston",
        race_name="Boston Marathon",
        race_date="2027-04-20",
        goal_marathon_s=3 * 3600 + 30 * 60,
        completed_marathon_time_s=3 * 3600 + 45 * 60,
    )
    assert new_survey.returning_marathoner is True
    assert new_survey.race_fit is True
    assert new_survey.race_date == "2027-04-20"
    assert new_survey.last_marathon_date == prior_survey.race_date
    assert new_survey.last_marathon_time_s == 3 * 3600 + 45 * 60
    # Demonstrated peak carried as p_history; w_now seeded below peak (recovered base).
    assert new_survey.p_history >= prior_plan.peak_miles
    assert new_survey.w_now < prior_plan.peak_miles
    assert new_survey.recent_sustained_mpw == round(prior_plan.peak_miles, 1)
    assert new_survey.secondary_races == []
    assert any("seed VDOT" in n for n in prov["notes"])
    # The seeded survey still builds a valid plan.
    assert build_plan(new_survey.to_athlete_inputs()).block_weeks == new_survey.block_weeks


def test_carry_forward_history_scan_can_raise_vdot(tmp_path: Path) -> None:
    prior_survey = _survey(vdot=38.0)
    resolved = prior_survey.to_athlete_inputs()
    prior_plan = build_plan(resolved)
    # A strong recent half marathon implies a higher VDOT than the prior calibrated 38.
    races = [{"category": "Half Marathon", "date": "2026-11-01", "duration_s": 5400}]
    new_survey, prov = build_next_season_survey(
        prior_survey, resolved, prior_plan,
        label="L", race_name="R", race_date="2027-04-20",
        goal_marathon_s=3 * 3600 + 30 * 60,
        races=races,
    )
    assert prov["history_effective_vdot"] is not None
    assert new_survey.vdot >= 38.0
