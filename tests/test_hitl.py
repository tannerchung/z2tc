"""Human-in-the-loop: stub LLM extraction, easy-pace → VDOT post-process, review CLI."""

from __future__ import annotations

import json
import os
from argparse import Namespace
from datetime import date
from pathlib import Path

import pytest

import main
from engine.plan.replan import replan
from llm.boundary import extract_events
from store.db import Store
from store.events import (
    EventRecord,
    SetRaceDatePayload,
    WeeklyEvaluationPayload,
    parse_event_payload,
)
from store.models import Athlete, SurveyInputs

REPO = Path(__file__).resolve().parents[1]
TRAINING_SYNTHETIC = REPO / "tests" / "fixtures" / "training_synthetic.jsonl"


def _plan_artifact_count(store: Store, athlete_id: str) -> int:
    row = store._conn.execute(
        "SELECT COUNT(*) AS c FROM plan_artifacts WHERE athlete_id = ?",
        (athlete_id,),
    ).fetchone()
    return int(row["c"]) if row else 0


def _minimal_survey() -> SurveyInputs:
    return SurveyInputs(
        name="Hitl",
        vdot=43.0,
        goal_marathon_s=4 * 3600,
        w_now=30.0,
        p_history=35.0,
        longest_run_mi=14.0,
        days_per_week=4,
        race_date="2026-10-10",
    )


def test_extract_events_stub_derives_vdot_from_easy_pace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.setenv(
        "Z2TC_LLM_STUB_EVENTS_JSON",
        json.dumps(
            [
                {
                    "kind": "WeeklyEvaluation",
                    "week_start": "2026-06-01",
                    "easy_pace_override_s": 570,
                    "note": "easy ~9:30",
                }
            ]
        ),
    )
    recs = extract_events(
        "ignored",
        athlete_id="a1",
        break_days=0,
        cross_trained=False,
        today=date(2026, 6, 1),
        race_date="2026-10-10",
        block_weeks=18,
    )
    assert len(recs) == 1
    p = recs[0].payload
    assert isinstance(p, WeeklyEvaluationPayload)
    assert p.easy_pace_override_s == 570
    assert p.calibrated_vdot is not None
    assert 40.0 <= float(p.calibrated_vdot) <= 46.0


def test_review_yes_all_approves_and_replans(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    db = Store(db_path=tmp_path / "hitl.db", project_root=tmp_path)
    aid = "hitl-1"
    db.upsert_athlete(Athlete(id=aid, name="Hitl", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    db.append_event_record(
        EventRecord(
            athlete_id=aid,
            source="llm",
            status="proposed",
            payload=WeeklyEvaluationPayload(
                week_start="2026-06-01",
                calibrated_vdot=48.0,
                note="test proposal",
            ),
        )
    )
    args = Namespace(athlete_id=aid, yes_all=True, no_replan=False, db=str(db.path))
    assert main._cmd_review(args) == 0
    rows = db.list_events(aid, status="proposed")
    assert len(rows) == 0
    plan = replan(_minimal_survey().to_athlete_inputs(), db, aid)
    assert plan.vdot == 48.0
    assert db.load_latest_plan(aid) is not None


def test_interpret_activities_writes_notes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.delenv("Z2TC_LLM_STUB_EVENTS_JSON", raising=False)
    jl = tmp_path / "tr.jsonl"
    week = {
        "iso_year": 2026,
        "iso_week": 10,
        "week_start": "2026-03-02",
        "workouts": [
            {
                "activity_id": "999",
                "name": "Morning Run",
                "description": "x" * 50,
                "sport_type": "Run",
                "start_date": "2026-03-04T12:00:00Z",
                "url": "https://strava.com/activities/999",
                "stats": {},
            }
        ],
    }
    jl.write_text(json.dumps(week) + "\n", encoding="utf-8")
    db = Store(db_path=tmp_path / "ia.db", project_root=tmp_path)
    aid = "ia-1"
    db.upsert_athlete(Athlete(id=aid, name="IA", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    args = Namespace(athlete_id=aid, training=jl, weeks=2, min_chars=10, db=str(db.path))
    assert main._cmd_interpret_activities(args) == 0
    notes = [r for r in db.list_events(aid) if r["event_type"] == "CoachNote"]
    assert len(notes) >= 1


@pytest.mark.skipif(not TRAINING_SYNTHETIC.exists(), reason="synthetic training fixture missing")
def test_interpret_activities_fixture_tags_and_stub_proposals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.setenv(
        "Z2TC_LLM_STUB_EVENTS_JSON",
        json.dumps([{"kind": "Difficulty", "delta": -1}]),
    )
    db = Store(db_path=tmp_path / "ia_syn.db", project_root=tmp_path)
    aid = "ia-syn"
    db.upsert_athlete(Athlete(id=aid, name="IA", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    args = Namespace(
        athlete_id=aid,
        training=TRAINING_SYNTHETIC,
        weeks=4,
        min_chars=40,
        db=str(db.path),
    )
    assert main._cmd_interpret_activities(args) == 0
    notes = [r for r in db.list_events(aid) if r["event_type"] == "CoachNote"]
    assert len(notes) >= 1
    tags: list[str] = []
    for r in notes:
        payload = parse_event_payload(json.loads(r["payload_json"]))
        tags.extend(getattr(payload, "tags", []) or [])
    assert "strava_activity" in tags
    assert "activity_id:syn-42" in tags
    proposed = db.list_events(aid, status="proposed")
    assert len(proposed) >= 1
    assert proposed[0]["event_type"] == "Difficulty"


def test_propose_notes_applied_coach_note_and_proposed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.setenv(
        "Z2TC_LLM_STUB_EVENTS_JSON",
        json.dumps([{"kind": "WeeklyEvaluation", "week_start": "2026-06-01", "note": "stub"}]),
    )
    db = Store(db_path=tmp_path / "pn.db", project_root=tmp_path)
    aid = "pn-1"
    db.upsert_athlete(Athlete(id=aid, name="PN", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    args = Namespace(
        athlete_id=aid,
        text="Coach says easy day tomorrow.",
        file=None,
        tag=None,
        db=str(db.path),
    )
    assert main._cmd_propose_notes(args) == 0
    applied_notes = [
        r
        for r in db.list_events(aid)
        if r["event_type"] == "CoachNote" and r["status"] == "applied"
    ]
    assert len(applied_notes) == 1
    proposed = db.list_events(aid, status="proposed")
    assert len(proposed) == 1


def test_propose_notes_reads_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.setenv(
        "Z2TC_LLM_STUB_EVENTS_JSON",
        json.dumps([{"kind": "Difficulty", "delta": 1}]),
    )
    fp = tmp_path / "note.txt"
    fp.write_text("  File body line 1.\nLine 2.\n", encoding="utf-8")
    db = Store(db_path=tmp_path / "pnf.db", project_root=tmp_path)
    aid = "pnf-1"
    db.upsert_athlete(Athlete(id=aid, name="PNF", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    args = Namespace(athlete_id=aid, text=None, file=fp, tag=None, db=str(db.path))
    assert main._cmd_propose_notes(args) == 0
    note_row = next(r for r in db.list_events(aid) if r["event_type"] == "CoachNote")
    body = parse_event_payload(json.loads(note_row["payload_json"])).text
    assert "File body line 1" in body
    assert len(db.list_events(aid, status="proposed")) == 1


def test_propose_notes_missing_file_returns_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    db = Store(db_path=tmp_path / "pnm.db", project_root=tmp_path)
    aid = "pnm-1"
    db.upsert_athlete(Athlete(id=aid, name="PNM", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    args = Namespace(
        athlete_id=aid,
        text=None,
        file=tmp_path / "nope.txt",
        tag=None,
        db=str(db.path),
    )
    assert main._cmd_propose_notes(args) == 1


def test_propose_notes_no_stub_records_only_coach_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.delenv("Z2TC_LLM_STUB_EVENTS_JSON", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    db = Store(db_path=tmp_path / "pns.db", project_root=tmp_path)
    aid = "pns-1"
    db.upsert_athlete(Athlete(id=aid, name="PNS", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    args = Namespace(athlete_id=aid, text="No LLM payloads.", file=None, tag=None, db=str(db.path))
    assert main._cmd_propose_notes(args) == 0
    assert len(db.list_events(aid, status="proposed")) == 0
    assert sum(1 for r in db.list_events(aid) if r["event_type"] == "CoachNote") == 1


def test_dossier_proposals_are_proposed_then_fold_only_after_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Step 2: the dossier feeds plan creation as *proposed* events — never a silent mutation. The
    # proposed ManualOverride is skipped by the fold until `review` approves it.
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from engine import athlete_profile as ap
    from engine.plan.replan import fold_events_to_inputs

    db = Store(db_path=tmp_path / "dos.db", project_root=tmp_path)
    aid = "dos-1"
    db.upsert_athlete(Athlete(id=aid, name="Dossier", strava_athlete_id=None))
    survey = _minimal_survey()
    db.save_survey_baseline(aid, survey)

    vol = ap.VolumeProfile(
        demonstrated_opener_mpw=24.0, sustainable_low_mpw=20.0, sustainable_high_mpw=35.0,
        peak_mpw=40.0, avg_active_mpw=28.0, long_run_dominance_pct=0.0, active_weeks=10,
    )
    proposals = ap.proposed_inputs(vol, current_opener_mpw=12.0, injury_prone=True)
    assert proposals and proposals[0].field == "reentry_start_mpw" and proposals[0].value == 24
    dossier = ap.AthleteDossier(
        name="Dossier",
        volume=vol,
        fitness=ap.FitnessTimeline(
            current_vdot=43.0, races=[], vdot_min=None, vdot_max=None,
            volume_vdot_corr=None, responder="insufficient-data", endurance_gap=None,
        ),
        goals=[],
        anchor=ap.AnchorConfidence(43.0, None, None, False, "n/a"),
        proposed_inputs=proposals,
    )

    assert main._write_dossier_proposals(db, aid, dossier) == 0
    # An applied provenance CoachNote + a proposed ManualOverride were logged.
    applied_notes = [r for r in db.list_events(aid) if r["event_type"] == "CoachNote" and r["status"] == "applied"]
    assert len(applied_notes) == 1
    proposed = db.list_events(aid, status="proposed")
    assert len(proposed) == 1 and proposed[0]["event_type"] == "ManualOverride"

    # Never silent: the proposed override does not affect the folded inputs until approved.
    folded, _ = fold_events_to_inputs(survey.to_athlete_inputs(), db, aid)
    assert folded.reentry_start_mpw != 24

    # After approval the same change folds in.
    assert main._cmd_review(Namespace(athlete_id=aid, yes_all=True, no_replan=True, db=str(db.path))) == 0
    assert not db.list_events(aid, status="proposed")
    folded2, _ = fold_events_to_inputs(survey.to_athlete_inputs(), db, aid)
    assert folded2.reentry_start_mpw == 24


def test_review_empty_queue_returns_0(tmp_path: Path) -> None:
    db = Store(db_path=tmp_path / "rev0.db", project_root=tmp_path)
    aid = "rev0"
    db.upsert_athlete(Athlete(id=aid, name="R0", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    args = Namespace(athlete_id=aid, yes_all=False, no_replan=False, db=str(db.path))
    assert main._cmd_review(args) == 0


def test_review_reject_marks_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.delenv("Z2TC_REVIEW_AUTO", raising=False)
    monkeypatch.setattr("builtins.input", lambda _p="": "r")
    db = Store(db_path=tmp_path / "revr.db", project_root=tmp_path)
    aid = "revr"
    db.upsert_athlete(Athlete(id=aid, name="RR", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    db.append_event_record(
        EventRecord(
            athlete_id=aid,
            source="llm",
            status="proposed",
            payload=WeeklyEvaluationPayload(week_start="2026-06-01", calibrated_vdot=55.0, note="x"),
        )
    )
    args = Namespace(athlete_id=aid, yes_all=False, no_replan=False, db=str(db.path))
    assert main._cmd_review(args) == 0
    assert not db.list_events(aid, status="proposed")
    rejected = [r for r in db.list_events(aid) if r["status"] == "rejected"]
    assert len(rejected) == 1


def test_review_skip_leaves_proposed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.delenv("Z2TC_REVIEW_AUTO", raising=False)
    monkeypatch.setattr("builtins.input", lambda _p="": "s")
    db = Store(db_path=tmp_path / "revs.db", project_root=tmp_path)
    aid = "revs"
    db.upsert_athlete(Athlete(id=aid, name="RS", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    db.append_event_record(
        EventRecord(
            athlete_id=aid,
            source="llm",
            status="proposed",
            payload=WeeklyEvaluationPayload(week_start="2026-06-01", calibrated_vdot=55.0, note="x"),
        )
    )
    args = Namespace(athlete_id=aid, yes_all=False, no_replan=False, db=str(db.path))
    assert main._cmd_review(args) == 0
    assert len(db.list_events(aid, status="proposed")) == 1


def test_review_no_replan_does_not_save_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    survey_path = REPO / "tests" / "fixtures" / "survey_kelly.json"
    if not survey_path.exists():
        pytest.skip("survey_kelly.json missing")
    db = Store(db_path=tmp_path / "nr.db", project_root=tmp_path)
    aid = "nr-1"
    assert (
        main._cmd_build_plan(
            Namespace(athlete_id=aid, survey=str(survey_path), strava_id=None, db=str(db.path))
        )
        == 0
    )
    assert _plan_artifact_count(db, aid) == 1
    db.append_event_record(
        EventRecord(
            athlete_id=aid,
            source="llm",
            status="proposed",
            payload=WeeklyEvaluationPayload(week_start="2026-06-01", calibrated_vdot=50.0, note="n"),
        )
    )
    args = Namespace(athlete_id=aid, yes_all=True, no_replan=True, db=str(db.path))
    assert main._cmd_review(args) == 0
    assert _plan_artifact_count(db, aid) == 1


def test_review_z2tc_review_auto_all(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.setenv("Z2TC_REVIEW_AUTO", "all")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def _no_input(_: str = "") -> str:
        raise AssertionError("input() should not be called when Z2TC_REVIEW_AUTO=all")

    monkeypatch.setattr("builtins.input", _no_input)
    db = Store(db_path=tmp_path / "auto.db", project_root=tmp_path)
    aid = "auto-1"
    db.upsert_athlete(Athlete(id=aid, name="Auto", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    db.append_event_record(
        EventRecord(
            athlete_id=aid,
            source="llm",
            status="proposed",
            payload=WeeklyEvaluationPayload(week_start="2026-06-01", calibrated_vdot=47.0, note="auto"),
        )
    )
    args = Namespace(athlete_id=aid, yes_all=False, no_replan=False, db=str(db.path))
    assert main._cmd_review(args) == 0
    assert not db.list_events(aid, status="proposed")


def test_interpret_activities_missing_training_returns_1(tmp_path: Path) -> None:
    db = Store(db_path=tmp_path / "badtr.db", project_root=tmp_path)
    aid = "badtr"
    db.upsert_athlete(Athlete(id=aid, name="B", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    args = Namespace(
        athlete_id=aid,
        training=tmp_path / "missing.jsonl",
        weeks=2,
        min_chars=10,
        db=str(db.path),
    )
    assert main._cmd_interpret_activities(args) == 1


def test_review_prints_date_warning_for_out_of_window_week_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("Z2TC_REVIEW_AUTO", raising=False)
    monkeypatch.setattr("builtins.input", lambda _p="": "s")
    db = Store(db_path=tmp_path / "rw_warn.db", project_root=tmp_path)
    aid = "rw-out"
    db.upsert_athlete(Athlete(id=aid, name="R", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    db.append_event_record(
        EventRecord(
            athlete_id=aid,
            source="llm",
            status="proposed",
            payload=WeeklyEvaluationPayload(
                week_start="2020-01-06",
                calibrated_vdot=40.0,
                note="bad week",
            ),
        )
    )
    assert (
        main._cmd_review(
            Namespace(athlete_id=aid, yes_all=False, no_replan=True, db=str(db.path))
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "date warning" in out
    assert "2020-01-06" in out


def test_review_no_date_warning_when_week_start_in_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("Z2TC_REVIEW_AUTO", raising=False)
    monkeypatch.setattr("builtins.input", lambda _p="": "s")
    db = Store(db_path=tmp_path / "rw_ok.db", project_root=tmp_path)
    aid = "rw-ok"
    db.upsert_athlete(Athlete(id=aid, name="R", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    db.append_event_record(
        EventRecord(
            athlete_id=aid,
            source="llm",
            status="proposed",
            payload=WeeklyEvaluationPayload(
                week_start="2026-06-01",
                calibrated_vdot=40.0,
                note="ok",
            ),
        )
    )
    assert (
        main._cmd_review(
            Namespace(athlete_id=aid, yes_all=False, no_replan=True, db=str(db.path))
        )
        == 0
    )
    assert "date warning" not in capsys.readouterr().out


def test_review_prints_date_warning_for_out_of_window_set_race_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("Z2TC_REVIEW_AUTO", raising=False)
    monkeypatch.setattr("builtins.input", lambda _p="": "s")
    db = Store(db_path=tmp_path / "rw_sr_bad.db", project_root=tmp_path)
    aid = "rw-sr-bad"
    db.upsert_athlete(Athlete(id=aid, name="R", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    db.append_event_record(
        EventRecord(
            athlete_id=aid,
            source="llm",
            status="proposed",
            payload=SetRaceDatePayload(race_date="2020-01-06"),
        )
    )
    assert (
        main._cmd_review(
            Namespace(athlete_id=aid, yes_all=False, no_replan=True, db=str(db.path))
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "date warning" in out
    assert "2020-01-06" in out


def test_review_no_date_warning_when_set_race_date_in_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("Z2TC_REVIEW_AUTO", raising=False)
    monkeypatch.setattr("builtins.input", lambda _p="": "s")
    db = Store(db_path=tmp_path / "rw_sr_ok.db", project_root=tmp_path)
    aid = "rw-sr-ok"
    db.upsert_athlete(Athlete(id=aid, name="R", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    db.append_event_record(
        EventRecord(
            athlete_id=aid,
            source="llm",
            status="proposed",
            payload=SetRaceDatePayload(race_date="2026-10-10"),
        )
    )
    assert (
        main._cmd_review(
            Namespace(athlete_id=aid, yes_all=False, no_replan=True, db=str(db.path))
        )
        == 0
    )
    assert "date warning" not in capsys.readouterr().out


def test_review_no_baseline_no_date_warning_no_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("Z2TC_REVIEW_AUTO", raising=False)
    monkeypatch.setattr("builtins.input", lambda _p="": "s")
    db = Store(db_path=tmp_path / "rw_nb.db", project_root=tmp_path)
    aid = "rw-nb"
    db.upsert_athlete(Athlete(id=aid, name="R", strava_athlete_id=None))
    db.append_event_record(
        EventRecord(
            athlete_id=aid,
            source="llm",
            status="proposed",
            payload=WeeklyEvaluationPayload(
                week_start="2020-01-06",
                calibrated_vdot=40.0,
                note="no survey",
            ),
        )
    )
    assert (
        main._cmd_review(
            Namespace(athlete_id=aid, yes_all=False, no_replan=True, db=str(db.path))
        )
        == 0
    )
    assert "date warning" not in capsys.readouterr().out


@pytest.mark.skipif(not os.environ.get("Z2TC_RUN_LIVE_GEMINI"), reason="set Z2TC_RUN_LIVE_GEMINI=1 to run")
def test_live_gemini_propose_notes_returns_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Opt-in smoke: one network call to Gemini; requires GEMINI_API_KEY or GOOGLE_API_KEY."""
    monkeypatch.delenv("Z2TC_DISABLE_GEMINI", raising=False)
    monkeypatch.delenv("Z2TC_LLM_STUB_EVENTS_JSON", raising=False)
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        pytest.skip("no Gemini API key in environment")
    db = Store(db_path=tmp_path / "live.db", project_root=tmp_path)
    aid = "live-gem-1"
    db.upsert_athlete(Athlete(id=aid, name="Live", strava_athlete_id=None))
    db.save_survey_baseline(aid, _minimal_survey())
    args = Namespace(
        athlete_id=aid,
        text="Easy pace about 9:45 per mile; minor left calf tightness; goal race in October.",
        file=None,
        tag=None,
        db=str(db.path),
    )
    assert main._cmd_propose_notes(args) == 0
    assert any(r["event_type"] == "CoachNote" for r in db.list_events(aid))


def test_latest_plan_vdot_changes_after_review_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before/after: approved WeeklyEvaluation updates folded VDOT in the saved artifact."""
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    survey_path = REPO / "tests" / "fixtures" / "survey_kelly.json"
    if not survey_path.exists():
        pytest.skip("survey_kelly.json missing")
    db = Store(db_path=tmp_path / "cmp.db", project_root=tmp_path)
    aid = "cmp-1"
    assert (
        main._cmd_build_plan(
            Namespace(athlete_id=aid, survey=str(survey_path), strava_id=None, db=str(db.path))
        )
        == 0
    )
    first = db.load_latest_plan(aid)
    assert first is not None
    v0 = float(first.plan_json.get("vdot", 0.0))
    db.append_event_record(
        EventRecord(
            athlete_id=aid,
            source="llm",
            status="proposed",
            payload=WeeklyEvaluationPayload(
                week_start="2026-06-01",
                calibrated_vdot=59.0,
                note="big bump for test",
            ),
        )
    )
    assert (
        main._cmd_review(Namespace(athlete_id=aid, yes_all=True, no_replan=False, db=str(db.path))) == 0
    )
    second = db.load_latest_plan(aid)
    assert second is not None
    v1 = float(second.plan_json.get("vdot", 0.0))
    assert v1 != v0
    assert v1 == 59.0
