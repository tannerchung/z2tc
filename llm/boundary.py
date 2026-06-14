"""Typed LLM boundary: NL and format dumps in, validated events / narrative / style out.

No live model in this repo build — ``stub_extract_events`` returns empty unless
``Z2TC_LLM_STUB_EVENTS_JSON`` is set (JSON array of event payload objects for tests).
The engine never trusts free text for numbers: payloads are validated with Pydantic.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from pydantic import BaseModel, Field

from store.events import EventRecord, EventSource, parse_event_payload


class PlanDiffSummary(BaseModel):
    """Structured diff for narrative (no per-mile authority)."""

    weeks_changed: int = 0
    peak_miles_before: float | None = None
    peak_miles_after: float | None = None
    method_before: str | None = None
    method_after: str | None = None


class StyleSpec(BaseModel):
    """Renderer-facing theme distilled from a workbook (MVP: sparse)."""

    title_font_family: str | None = None
    title_font_size: int | None = None
    header_rgb: tuple[float, float, float] | None = None
    notes: str = ""


def stub_extract_events(_text: str, *, athlete_id: str, source: EventSource = "llm") -> list[EventRecord]:
    raw = os.environ.get("Z2TC_LLM_STUB_EVENTS_JSON", "").strip()
    if not raw:
        return []
    payloads = json.loads(raw)
    out: list[EventRecord] = []
    for p in payloads:
        ev = parse_event_payload(p)
        out.append(EventRecord(athlete_id=athlete_id, source=source, status="proposed", payload=ev))
    return out


def extract_events(text: str, *, athlete_id: str, source: EventSource = "llm") -> list[EventRecord]:
    """NL -> proposed events (stub unless env provides JSON payloads)."""
    return stub_extract_events(text, athlete_id=athlete_id, source=source)


def narrate(diff: PlanDiffSummary) -> str:
    """Structured diff -> coach-facing blurb (no numbers invented)."""
    parts = []
    if diff.weeks_changed:
        parts.append(f"Week structure changed in {diff.weeks_changed} place(s).")
    if diff.peak_miles_before is not None and diff.peak_miles_after is not None:
        parts.append(
            f"Peak volume moved from {diff.peak_miles_before:g} to {diff.peak_miles_after:g} mpw."
        )
    if diff.method_before and diff.method_after and diff.method_before != diff.method_after:
        parts.append(f"Method switched from {diff.method_before} to {diff.method_after}.")
    return " ".join(parts) if parts else "No material plan changes detected."


def extract_style(format_dump: dict[str, Any], *, use_llm_assist: bool = False) -> StyleSpec:
    """Heuristic style from harvested grid data; ``use_llm_assist`` reserved for later."""
    _ = use_llm_assist
    spec = StyleSpec(notes="derived_heuristic")
    # If dump contains sampled title styles, pick first font/size (MVP).
    tabs = format_dump.get("tabs") or []
    for tab in tabs:
        for cell in tab.get("sample_cells") or []:
            fmt = cell.get("userEnteredFormat") or {}
            t = fmt.get("textFormat") or {}
            if t.get("fontSize") and spec.title_font_size is None:
                spec.title_font_size = int(t["fontSize"])
            if t.get("fontFamily") and spec.title_font_family is None:
                spec.title_font_family = str(t["fontFamily"])
            if spec.title_font_size and spec.title_font_family:
                return spec
    return spec


def validate_no_numeric_authority(text: str) -> None:
    """Reject strings that look like they assert paces/miles (coarse guard for LLM output)."""
    if re.search(r"\b\d{1,2}:\d{2}\s*/mi\b", text, re.I):
        raise ValueError("LLM output must not include pace numbers")
    if re.search(r"\b\d{2}\.?\d*\s*mpw\b", text, re.I):
        raise ValueError("LLM output must not include mpw numbers")
