"""Tests for ``store.merge_survey`` (returning marathoner merge path)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from store.merge_survey import detect_returning_marathoner, merge_strava_report
from store.models import SurveyInputs

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "survey_kelly.json"


def _base() -> SurveyInputs:
    return SurveyInputs.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def test_detect_returning_from_report() -> None:
    base = _base()
    assert not detect_returning_marathoner(base, {})
    assert detect_returning_marathoner(
        base, {"latest_marathon": {"date": "2025-10-11"}}
    )


def test_detect_returning_from_intake_marathon_time() -> None:
    base = _base().model_copy(update={"latest_marathon_time_s": 14400})
    assert detect_returning_marathoner(base, {})


def test_detect_returning_from_intake_flag() -> None:
    base = _base().model_copy(update={"returning_marathoner": True})
    assert detect_returning_marathoner(base, {})


def test_merge_applies_decay_and_flags(tmp_path: Path) -> None:
    report_path = Path(__file__).resolve().parents[1] / "output" / "marathon" / "report_128394498.json"
    training_path = Path(__file__).resolve().parents[1] / "output" / "marathon" / "training_128394498.jsonl"
    if not report_path.exists() or not training_path.exists():
        pytest.skip("Cindy Strava artifacts not on disk")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    weeks = [json.loads(line) for line in training_path.read_text().splitlines() if line.strip()]
    base = SurveyInputs(
        name="Cindy Kim",
        vdot=40.0,
        goal_marathon_s=13800,
        w_now=10.0,
        p_history=20.0,
        longest_run_mi=10.0,
        days_per_week=4,
        race_date="2026-10-11",
        race_name="Chicago Marathon",
    )
    merged, prov = merge_strava_report(
        base,
        report,
        weeks,
        today=date(2026, 6, 15),
        chip_search_name=None,
        returning_marathoner=True,
    )
    assert merged.returning_marathoner
    assert merged.race_fit
    assert merged.p_history > 30
    assert merged.last_marathon_date == "2025-10-11"
    assert merged.decayed_peak_mpw is not None
    assert merged.decayed_peak_mpw < merged.p_history
    assert merged.recent_break_days < 21
    assert merged.vdot > 32.0
    assert any("returning marathoner" in p for p in prov)
    assert any("fitness_race" in p for p in prov)
