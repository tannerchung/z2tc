"""Tests for the narrative capture / versioning layer (engine/narrative_capture.py + store + CLI).

Locks the deterministic-vs-LLM record shape, the per-surface aggregation that drives the distillation
loop, the store roundtrip, and that capture is side-effect-only (never changes the rendered plan)."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

import main
from engine.narrative_capture import (
    NarrativeRender,
    build_narrative_captures,
    summarize_surface_stats,
)
from store.db import SCHEMA_VERSION, Store
from store.models import Athlete, SurveyInputs


def _det() -> dict[str, str]:
    return {"summary": "18-week plan at VDOT 45.", "personalized": "Speed sits ahead of endurance.", "notes": ""}


def test_build_captures_deterministic_path():
    caps = build_narrative_captures(
        _det(), {}, athlete_id="a1", template_version="1", llm_applied=False,
    )
    # Empty surfaces are skipped; non-empty ones are recorded as deterministic with no model/prompt.
    assert {c.surface for c in caps} == {"summary", "personalized"}
    for c in caps:
        assert c.source == "deterministic"
        assert c.final_text == c.deterministic_text and not c.changed
        assert c.llm_model is None and c.prompt_version is None


def test_build_captures_llm_changed_and_noop():
    final = {
        "summary": "An 18-week plan built around VDOT 45.",   # reworded, same numbers
        "personalized": "Speed sits ahead of endurance.",      # byte-identical → LLM no-op
    }
    caps = {c.surface: c for c in build_narrative_captures(
        _det(), final, athlete_id="a1", template_version="1", llm_applied=True,
        llm_model="stub", prompt_version="p1", signals={"responder": "speed-dominant", "blank": ""},
    )}
    assert caps["summary"].source == "llm" and caps["summary"].changed
    assert caps["summary"].char_delta == len(final["summary"]) - len(_det()["summary"])
    assert caps["summary"].llm_model == "stub" and caps["summary"].prompt_version == "p1"
    assert caps["summary"].signals == {"responder": "speed-dominant"}   # empty signal dropped
    # Identical LLM output is still source=llm but changed=False (the "LLM no-op" signal).
    assert caps["personalized"].source == "llm" and not caps["personalized"].changed


def test_summarize_surface_stats_flags_deterministic_candidate():
    rows = []
    # summary: 6 LLM renders, only 1 changed → 0.167 < 0.2 and n>=5 → candidate
    for i in range(6):
        rows.append({"surface": "summary", "source": "llm", "changed": i == 0, "char_delta": 5, "guard_passed": True})
    # notes: 6 LLM renders, 5 changed → not a candidate; one guard failure
    for i in range(6):
        rows.append({"surface": "notes", "source": "llm", "changed": i < 5, "char_delta": -40, "guard_passed": i != 0})
    stats = {s.surface: s for s in summarize_surface_stats(rows)}
    assert stats["summary"].llm_change_rate == round(1 / 6, 3)
    assert stats["summary"].deterministic_candidate is True
    assert stats["notes"].deterministic_candidate is False
    assert stats["notes"].guard_failures == 1
    assert stats["notes"].mean_abs_char_delta == 40.0


def test_store_roundtrip_and_schema_version(tmp_path: Path):
    db = Store(db_path=tmp_path / "narr.db", project_root=tmp_path)
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    db.upsert_athlete(Athlete(id="a1", name="A", strava_athlete_id=None))
    rec = NarrativeRender(
        athlete_id="a1", surface="summary", template_version="1", source="llm",
        deterministic_text="x", final_text="xy", changed=True, char_delta=1,
        prompt_version="p1", llm_model="stub", signals={"responder": "stable"},
    )
    db.append_narrative_render(rec)
    rows = db.list_narrative_renders("a1")
    assert len(rows) == 1
    r = dict(rows[0])
    assert r["surface"] == "summary" and r["source"] == "llm" and r["changed"] == 1
    assert r["prompt_version"] == "p1" and r["llm_model"] == "stub"
    assert r["plan_artifact_id"] is None        # unset by default
    # Fleet-wide read (no athlete filter) and surface filter both work.
    assert len(db.list_narrative_renders()) == 1
    assert len(db.list_narrative_renders(surface="notes")) == 0


def test_publication_links_plan_artifact_and_narrative(tmp_path: Path):
    from engine.plan import ENGINE_VERSION, build_plan
    from store.db import fingerprint_athlete_inputs
    from store.models import Publication

    db = Store(db_path=tmp_path / "pub.db", project_root=tmp_path)
    survey = SurveyInputs(
        name="Pub", vdot=45.0, goal_marathon_s=3 * 3600 + 30 * 60, w_now=30.0,
        p_history=42.0, longest_run_mi=16.0, days_per_week=5, race_date="2026-11-01",
    )
    db.upsert_athlete(Athlete(id="a1", name="Pub", strava_athlete_id=None))
    db.save_survey_baseline("a1", survey)
    inputs = survey.to_athlete_inputs()
    art_id = db.save_plan_artifact("a1", build_plan(inputs), fingerprint_athlete_inputs(inputs))

    # A narrative render linked to the published artifact joins back to it.
    db.append_narrative_render(NarrativeRender(
        athlete_id="a1", surface="summary", template_version="1", source="llm",
        deterministic_text="x", final_text="xy", changed=True, char_delta=1,
        prompt_version="p1", llm_model="stub", plan_artifact_id=art_id,
    ))
    assert dict(db.list_narrative_renders("a1")[0])["plan_artifact_id"] == art_id

    pub_id = db.record_publication(Publication(
        athlete_id="a1", plan_artifact_id=art_id, spreadsheet_id="SS", sheet_title="Z2TC_Pub",
        url="https://docs.google.com/spreadsheets/d/SS/edit", engine_version=ENGINE_VERSION,
        template_version="1", prompt_version="p1", llm_model="stub", narrative_source="llm",
        rows_written=42, meta={"weeks": 18, "layout": "plan_sheet"},
    ))
    rows = db.list_publications("a1")
    assert len(rows) == 1
    r = dict(rows[0])
    assert r["id"] == pub_id
    assert r["plan_artifact_id"] == art_id and r["spreadsheet_id"] == "SS"
    assert r["engine_version"] == ENGINE_VERSION and r["narrative_source"] == "llm"
    assert r["rows_written"] == 42
    # Filtering by the artifact returns the same publication (the lineage join).
    assert [dict(x)["id"] for x in db.list_publications(plan_artifact_id=art_id)] == [pub_id]


def test_publish_capture_does_not_change_render_and_populates_sink():
    from engine.plan import build_plan
    from render.plan_layout import NARRATIVE_TEMPLATE_VERSION, build_plan_sheet

    inputs = SurveyInputs(
        name="Cap Test", vdot=45.0, goal_marathon_s=3 * 3600 + 30 * 60, w_now=30.0,
        p_history=42.0, longest_run_mi=16.0, days_per_week=5, race_date="2026-11-01",
    ).to_athlete_inputs()
    plan = build_plan(inputs)

    plain = build_plan_sheet(plan, inputs).values
    sink: list = []
    captured = build_plan_sheet(plan, inputs, capture=sink).values
    assert captured == plain                       # capture is side-effect-only
    surfaces = {c.surface for c in sink}
    assert "summary" in surfaces                   # at least the always-present summary
    for c in sink:
        assert c.source == "deterministic"         # llm disabled by default
        assert c.template_version == NARRATIVE_TEMPLATE_VERSION
        assert c.inputs_fingerprint                 # fingerprint recorded


def test_capture_records_llm_source_when_smoothed(monkeypatch: pytest.MonkeyPatch):
    import json as _json

    from engine.plan import build_plan
    from render.plan_layout import build_plan_sheet

    inputs = SurveyInputs(
        name="Smoothed", vdot=45.0, goal_marathon_s=3 * 3600 + 30 * 60, w_now=30.0,
        p_history=42.0, longest_run_mi=16.0, days_per_week=5, race_date="2026-11-01",
    ).to_athlete_inputs()
    plan = build_plan(inputs)
    det_summary = build_plan_sheet(plan, inputs).rows[2].cells[0]  # the narrative row text

    # Stub rephrases the summary, preserving its numbers (the guard would reject new figures).
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.setenv("Z2TC_LLM_STUB_NARRATIVE_JSON", _json.dumps({"summary": det_summary + " You've got this."}))
    sink: list = []
    build_plan_sheet(plan, inputs, llm_narrative=True, capture=sink)
    summary_cap = next(c for c in sink if c.surface == "summary")
    assert summary_cap.source == "llm" and summary_cap.changed
    assert summary_cap.llm_model == "stub" and summary_cap.prompt_version == "p1"


def test_narrative_log_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    db = Store(db_path=tmp_path / "nl.db", project_root=tmp_path)
    db.upsert_athlete(Athlete(id="a1", name="A", strava_athlete_id=None))
    for i in range(5):
        db.append_narrative_render(NarrativeRender(
            athlete_id="a1", surface="summary", template_version="1", source="llm",
            deterministic_text="x", final_text="x", changed=False, char_delta=0,
            prompt_version="p1", llm_model="stub",
        ))
    rc = main._cmd_narrative_log(
        Namespace(athlete_id="a1", surface=None, limit=None, json=False, db=str(db.path))
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "summary" in out and "candidate" in out

    # Empty scope returns 0 with a friendly message.
    rc2 = main._cmd_narrative_log(
        Namespace(athlete_id="ghost", surface=None, limit=None, json=False, db=str(db.path))
    )
    assert rc2 == 0
