"""Golden subset: Kelly survey fixture → Store → build_plan → plan_artifact JSON shape."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.plan import build_plan
from store.db import Store, fingerprint_athlete_inputs
from store.models import Athlete, SurveyInputs

REPO = Path(__file__).resolve().parents[1]
SURVEY_PATH = REPO / "tests" / "fixtures" / "survey_kelly.json"


@pytest.mark.skipif(not SURVEY_PATH.exists(), reason="survey fixture missing")
def test_kelly_survey_plan_artifact_golden_subset(tmp_path: Path) -> None:
    """Locks stable plan shape for the fixture (vdot, block length, goal race) without full JSON."""
    survey = SurveyInputs.model_validate_json(SURVEY_PATH.read_text(encoding="utf-8"))
    db = Store(db_path=tmp_path / "golden.db", project_root=tmp_path)
    aid = "kelly-golden"
    db.upsert_athlete(Athlete(id=aid, name=survey.name, strava_athlete_id=None))
    db.save_survey_baseline(aid, survey)
    inputs = survey.to_athlete_inputs()
    plan = build_plan(inputs)
    fp = fingerprint_athlete_inputs(inputs)
    db.save_plan_artifact(aid, plan, fp)
    art = db.load_latest_plan(aid)
    assert art is not None
    pj = art.plan_json
    assert pj["block_weeks"] == 18
    assert pj["vdot"] == pytest.approx(43.0)
    assert pj["goal"]["date"] == "2026-10-10"
    assert len(pj["weeks"]) == 18
    assert pj["weeks"][0]["index"] == 1
    assert pj["weeks"][-1]["index"] == 18


def test_analyze_minimal_training_jsonl_summarizes_weekly_miles(tmp_path: Path) -> None:
    """``load_weeks`` + ``summarize`` on a tiny synthetic JSONL (no Strava)."""
    from engine.analyze import load_weeks, summarize

    week = {
        "week_start": "2026-06-01",
        "workouts": [
            {
                "sport_type": "Run",
                "start_date": "2026-06-01T10:00:00Z",
                "name": "Easy",
                "stats": {"Distance": "5.0 mi"},
            }
        ],
    }
    p = tmp_path / "tiny.jsonl"
    p.write_text(json.dumps(week) + "\n", encoding="utf-8")
    weeks = load_weeks(p)
    summary = summarize(weeks)
    assert summary.weeks == 1
    assert summary.weekly_run_miles.get("2026-06-01") == pytest.approx(5.0)
    assert summary.total_run_miles == pytest.approx(5.0)
