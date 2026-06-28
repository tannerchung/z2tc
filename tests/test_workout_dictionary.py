"""The club Workout Dictionary tab is generated from the engine catalog (no drift)."""

from __future__ import annotations

from engine.plan.workouts import CATALOG_WORKOUTS
from render.plan_sheet_theme import PlanSheetTheme
from render.workout_dictionary import (
    build_workout_dictionary_format_requests,
    build_workout_dictionary_layout,
)
from render.workout_glossary import PACE_LEGEND, STATIC_GLOSSARY


def test_dictionary_covers_every_catalog_workout():
    # Every named session the engine can rotate through must appear, with its definition and the
    # how-it's-built note, so the tab never drifts from what the plans prescribe.
    layout = build_workout_dictionary_layout()
    workout_rows = [r for r in layout.rows if r.kind == "workout"]
    names = {r.cells[0] for r in workout_rows}
    for w in CATALOG_WORKOUTS:
        assert w.name in names, w.name
    # Each workout row carries a non-empty purpose and generation note.
    for r in workout_rows:
        assert r.cells[1].strip() and r.cells[2].strip(), r.cells[0]


def test_dictionary_includes_paces_and_terminology():
    layout = build_workout_dictionary_layout()
    terms = {r.cells[0] for r in layout.rows if r.kind == "term"}
    assert "Easy (E)" in terms and "Threshold (T)" in terms
    for static_term, _ in STATIC_GLOSSARY:
        assert static_term in terms, static_term
    # Pace meanings come straight from the shared legend.
    pace_meanings = {r.cells[1] for r in layout.rows if r.kind == "term"}
    assert PACE_LEGEND["E"] in pace_meanings


def test_dictionary_is_deterministic():
    a = build_workout_dictionary_layout()
    b = build_workout_dictionary_layout()
    assert a.values == b.values


def test_dictionary_copy_avoids_em_dashes():
    # Athlete-facing tab: keep the house tone (no em dashes in the rendered cells).
    layout = build_workout_dictionary_layout()
    for row in layout.rows:
        for cell in row.cells:
            assert "\u2014" not in cell, row


def test_dictionary_format_requests_build():
    layout = build_workout_dictionary_layout()
    reqs = build_workout_dictionary_format_requests(7, layout, PlanSheetTheme())
    assert reqs
    assert any("mergeCells" in r for r in reqs)
    assert any(r.get("updateSheetProperties", {}).get("properties", {}).get("gridProperties") for r in reqs)
