"""Typed LLM boundary: NL and format dumps in, validated events / narrative / style out.

``extract_events`` prefers Gemini when ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY`` is set;
otherwise ``Z2TC_LLM_STUB_EVENTS_JSON`` (JSON array of event payload objects) supplies
test payloads. The engine never trusts free text for numbers: payloads are validated
with Pydantic; race VDOTs and detraining are recomputed in code.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engine.personalization import PersonalizationContext

from pydantic import BaseModel, Field

from engine import readiness as rd
from engine.paces import vdot_from_easy_pace
from engine.vdot import RACE_METERS, vdot_from_race
from store.events import (
    EventPayload,
    EventRecord,
    EventSource,
    RaceEstimatePayload,
    WeeklyEvaluationPayload,
    parse_event_payload,
)


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


_EXTRACT_SYSTEM = """You are a coaching assistant for a marathon training platform.
Read the coach or athlete text and emit a JSON array ONLY (no markdown, no prose) of
event objects. Each object must include \"kind\" matching one of the allowed kinds and
all required fields for that kind.

Allowed kinds and required fields:
- WeeklyEvaluation: week_start (ISO date Monday YYYY-MM-DD), optional calibrated_vdot,
  estimated_mpw, easy_pace_override_s (easy pace seconds per mile as integer),
  note (string). Use easy_pace_override_s when the text gives an easy pace; do not invent
  calibrated_vdot unless the text implies fitness from that pace (we will derive VDOT
  from easy pace in code when needed).
- EffortQuality: race_date (YYYY-MM-DD), quality one of max|submaximal|compromised, note.
- Injury: area (string), severity 1-5, optional days_off.
- Difficulty: delta integer -2 to 2.
- RaceEstimate: race_name, race_date (YYYY-MM-DD), distance_m (float meters: 5000,
  10000, 21097.5, or 42195), estimated_time_s (finish time seconds, coach-corrected),
  optional actual_time_s, note. Do NOT include estimated_vdot or effective_vdot; code
  computes them.
- ManualOverride: field (must be a valid AthleteInputs dataclass field name), value
  (JSON type matching that field).

Omit kinds that are not clearly supported by the text. Return [] if nothing applies."""


def _gemini_api_key() -> str | None:
    k = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    return k or None


def _gemini_model_name() -> str:
    return (os.environ.get("Z2TC_GEMINI_MODEL") or "gemini-3.5-flash").strip()


def _parse_iso_date(value: str) -> date | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _date_window(today: date, race_date_str: str | None, block_weeks: int | None) -> tuple[date, date]:
    """Plausible calendar span for LLM-emitted dates (UTC calendar dates)."""
    rd = _parse_iso_date(race_date_str or "")
    if rd is None:
        return today - timedelta(days=365), today + timedelta(days=365)
    bw = block_weeks if block_weeks is not None else 18
    span_days = max(1, int(bw)) * 7 + 14
    return rd - timedelta(days=span_days), rd + timedelta(days=14)


def date_window(today: date, race_date: str | None, block_weeks: int | None) -> tuple[date, date]:
    """Public: plausible ISO-date window for extraction/review (see docs)."""
    return _date_window(today, race_date, block_weeks)


def _date_in_window(value: str, window: tuple[date, date]) -> bool | None:
    """True in-window, False out-of-window, None if unparseable."""
    d = _parse_iso_date(value)
    if d is None:
        return None
    lo, hi = window
    return lo <= d <= hi


def _build_grounding(today: date, race_date_str: str | None, block_weeks: int | None) -> str:
    parts = [f"Today is {today.isoformat()} (UTC calendar date)."]
    rd = _parse_iso_date(race_date_str or "")
    if rd is not None:
        lo, hi = _date_window(today, race_date_str, block_weeks)
        parts.append(
            f"The athlete's goal race is {rd.isoformat()}. "
            f"The current training block spans roughly {lo.isoformat()}..{hi.isoformat()}."
        )
    else:
        lo, hi = _date_window(today, None, None)
        parts.append(
            f"No goal race date on file; prefer dates between {lo.isoformat()} and {hi.isoformat()}."
        )
    parts.append(
        "Use 4-digit ISO dates (YYYY-MM-DD). When the coach text omits a year, "
        "infer a year that places the event inside the block window above."
    )
    return " ".join(parts) + "\n\n"


def _payload_date_fields(payload: EventPayload) -> list[tuple[str, str]]:
    k = payload.kind
    if k == "WeeklyEvaluation":
        return [("week_start", getattr(payload, "week_start", ""))]
    if k == "RaceEstimate":
        return [("race_date", getattr(payload, "race_date", ""))]
    if k == "EffortQuality":
        return [("race_date", getattr(payload, "race_date", ""))]
    if k == "DataExclude":
        return [("race_date", getattr(payload, "race_date", ""))]
    if k == "FitnessAnchor":
        rd = getattr(payload, "race_date", None)
        if rd is None or not str(rd).strip():
            return []
        return [("race_date", str(rd))]
    if k == "SetRaceDate":
        return [("race_date", getattr(payload, "race_date", ""))]
    if k == "Unavailable":
        return [
            ("start", getattr(payload, "start", "")),
            ("end", getattr(payload, "end", "")),
        ]
    return []


def payload_out_of_window_fields(payload: EventPayload, window: tuple[date, date]) -> list[tuple[str, str]]:
    """Date fields on ``payload`` that parse as ISO dates and fall outside ``window``."""
    out: list[tuple[str, str]] = []
    for field_name, raw in _payload_date_fields(payload):
        if _date_in_window(raw, window) is False:
            out.append((field_name, raw))
    return out


def _mondays_in_window(lo: date, hi: date) -> list[date]:
    """ISO Mondays with ``lo <= Monday <= hi``."""
    m = lo + timedelta(days=(7 - lo.weekday()) % 7)
    if m < lo:
        m += timedelta(days=7)
    out: list[date] = []
    while m <= hi:
        out.append(m)
        m += timedelta(days=7)
    return out


def _resolve_calendar_date_into_window(d: date, window: tuple[date, date], field_name: str) -> date:
    """Map an out-of-window calendar day into ``window`` (deterministic). ``week_start`` → nearest Monday in window."""
    lo, hi = window
    if lo <= d <= hi:
        return d
    same_md: list[date] = []
    for y in range(lo.year - 1, hi.year + 2):
        try:
            c = date(y, d.month, d.day)
        except ValueError:
            continue
        if lo <= c <= hi:
            same_md.append(c)
    if not same_md:
        base = lo if d < lo else hi
    elif len(same_md) == 1:
        base = same_md[0]
    else:
        base = min(same_md, key=lambda c: (abs((c - d).days), c.isoformat()))
    if field_name == "week_start":
        mondays = _mondays_in_window(lo, hi)
        if not mondays:
            return base
        return min(mondays, key=lambda m: (abs((m - base).days), m.isoformat()))
    return base


def normalize_payload_calendar_dates(payload: EventPayload, window: tuple[date, date]) -> tuple[EventPayload, bool]:
    """Rewrite parseable grounded calendar fields that sit outside ``window`` (Phase 7).

    In-window values are left unchanged (including non-Monday ``week_start``). Unavailable
    ``start``/``end`` are repaired if normalization inverts the range.
    """
    updates: dict[str, str] = {}
    for fname, raw in _payload_date_fields(payload):
        d = _parse_iso_date(raw)
        if d is None:
            continue
        new_d = _resolve_calendar_date_into_window(d, window, fname)
        new_s = new_d.isoformat()
        old_key = str(raw or "").strip()[:10]
        if old_key != new_s:
            updates[fname] = new_s
    if not updates:
        return payload, False
    new_payload = payload.model_copy(update=updates)
    if getattr(new_payload, "kind", None) == "Unavailable":
        us = _parse_iso_date(getattr(new_payload, "start", ""))
        ue = _parse_iso_date(getattr(new_payload, "end", ""))
        if us is not None and ue is not None and us > ue:
            new_payload = new_payload.model_copy(update={"end": new_payload.start})
    return new_payload, True


def _normalize_proposed_records(athlete_id: str, records: list[EventRecord], window: tuple[date, date]) -> list[EventRecord]:
    out: list[EventRecord] = []
    for rec in records:
        old = rec.payload
        new_p, did = normalize_payload_calendar_dates(old, window)
        if did:
            for fname, raw_old in _payload_date_fields(old):
                raw_new = next((v for n, v in _payload_date_fields(new_p) if n == fname), None)
                if raw_new is not None and str(raw_old or "").strip()[:10] != str(raw_new or "").strip()[:10]:
                    print(
                        f"Date normalized (athlete={athlete_id}, kind={old.kind}, field={fname}, "
                        f"was={raw_old!r}, now={raw_new!r}).",
                        file=sys.stderr,
                    )
        out.append(rec.model_copy(update={"payload": new_p}) if did else rec)
    return out


def _apply_date_flags(athlete_id: str, records: list[EventRecord], window: tuple[date, date]) -> list[EventRecord]:
    lo, hi = window
    for rec in records:
        for field_name, raw in payload_out_of_window_fields(rec.payload, window):
            print(
                f"Date flag (athlete={athlete_id}, kind={rec.payload.kind}, field={field_name}, "
                f"value={raw!r}): outside plausible window {lo.isoformat()}..{hi.isoformat()}; "
                "keeping as proposed for review.",
                file=sys.stderr,
            )
    return records


def _strip_json_fence(raw: str) -> str:
    t = raw.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.I)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _parse_hms_to_seconds(value: str) -> int | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        parts = [int(p) for p in value.split(":")]
    except ValueError:
        return None
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0, parts[0], parts[1]
    else:
        return None
    return h * 3600 + m * 60 + s


def _normalize_distance_m(data: dict[str, Any]) -> float | None:
    if "distance_m" in data and isinstance(data["distance_m"], (int, float)):
        return float(data["distance_m"])
    label = str(data.get("distance") or data.get("race_distance") or "").strip().lower()
    mapping = {
        "5k": RACE_METERS["5K"],
        "10k": RACE_METERS["10K"],
        "half": RACE_METERS["Half Marathon"],
        "half marathon": RACE_METERS["Half Marathon"],
        "marathon": RACE_METERS["Marathon"],
    }
    if label in mapping:
        return mapping[label]
    for k, v in RACE_METERS.items():
        if k.lower() == label:
            return v
    return None


def _finalize_payload(p: EventPayload, *, break_days: int, cross_trained: bool) -> EventPayload:
    if isinstance(p, WeeklyEvaluationPayload):
        if p.easy_pace_override_s is not None and p.calibrated_vdot is None:
            v = vdot_from_easy_pace(int(p.easy_pace_override_s))
            return p.model_copy(update={"calibrated_vdot": v})
        return p
    if isinstance(p, RaceEstimatePayload):
        est_s = p.estimated_time_s
        if est_s <= 0:
            return p
        dist_m = float(p.distance_m)
        est_v = vdot_from_race(dist_m, float(est_s))
        if est_v is None:
            return p
        eff = rd.adjusted_vdot(est_v, int(break_days or 0), cross_trained)
        return p.model_copy(
            update={
                "estimated_vdot": float(est_v),
                "effective_vdot": float(eff),
                "break_days": int(break_days or 0),
            }
        )
    return p


def _dict_to_payload(data: dict[str, Any], *, break_days: int, cross_trained: bool) -> EventPayload | None:
    kind = data.get("kind")
    if kind == "RaceEstimate":
        dist_m = _normalize_distance_m(data)
        if dist_m is None:
            return None
        est_s = data.get("estimated_time_s")
        if isinstance(est_s, str):
            est_s = _parse_hms_to_seconds(est_s)
        if not isinstance(est_s, int) or est_s <= 0:
            return None
        act = data.get("actual_time_s")
        if isinstance(act, str):
            act = _parse_hms_to_seconds(act)
        act_s = int(act) if isinstance(act, int) else None
        note = str(data.get("note") or "")
        rd_out = RaceEstimatePayload(
            race_name=str(data.get("race_name") or "race"),
            race_date=str(data.get("race_date") or ""),
            distance_m=dist_m,
            actual_time_s=act_s,
            estimated_time_s=int(est_s),
            estimated_vdot=0.0,
            effective_vdot=0.0,
            break_days=int(break_days or 0),
            note=note,
        )
        return _finalize_payload(rd_out, break_days=break_days, cross_trained=cross_trained)
    try:
        base = parse_event_payload(data)
    except (ValueError, TypeError):
        return None
    return _finalize_payload(base, break_days=break_days, cross_trained=cross_trained)


def _gemini_parse_payloads(raw_text: str, *, break_days: int, cross_trained: bool) -> list[EventPayload]:
    blob = _strip_json_fence(raw_text)
    data = json.loads(blob)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    out: list[EventPayload] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        p = _dict_to_payload(item, break_days=break_days, cross_trained=cross_trained)
        if p is not None:
            out.append(p)
    return out


def _gemini_complete_json(prompt: str) -> str | None:
    """Run one Gemini JSON completion for ``prompt`` (full prompt, no extra system framing)."""
    key = _gemini_api_key()
    if not key:
        return None
    try:
        import google.generativeai as genai  # type: ignore[import-untyped]
    except ImportError:
        return None
    genai.configure(api_key=key)
    model = genai.GenerativeModel(_gemini_model_name())
    resp = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"},
        request_options={"timeout": 120},
    )
    text = (getattr(resp, "text", None) or "").strip()
    return text or None


def _gemini_generate_json(
    user_text: str,
    *,
    today: date | None = None,
    race_date: str | None = None,
    block_weeks: int | None = None,
) -> str | None:
    td = today if today is not None else datetime.now(timezone.utc).date()
    ground = _build_grounding(td, race_date, block_weeks)
    prompt = _EXTRACT_SYSTEM + "\n\n" + ground + "Coach/athlete text:\n" + user_text
    return _gemini_complete_json(prompt)


def stub_extract_events(
    _text: str,
    *,
    athlete_id: str,
    source: EventSource = "llm",
    break_days: int = 0,
    cross_trained: bool = False,
) -> list[EventRecord]:
    raw = os.environ.get("Z2TC_LLM_STUB_EVENTS_JSON", "").strip()
    if not raw:
        return []
    payloads = json.loads(raw)
    out: list[EventRecord] = []
    for p in payloads:
        ev = parse_event_payload(p)
        ev = _finalize_payload(ev, break_days=break_days, cross_trained=cross_trained)
        out.append(EventRecord(athlete_id=athlete_id, source=source, status="proposed", payload=ev))
    return out


def extract_events(
    text: str,
    *,
    athlete_id: str,
    source: EventSource = "llm",
    break_days: int = 0,
    cross_trained: bool = False,
    today: date | None = None,
    race_date: str | None = None,
    block_weeks: int | None = None,
) -> list[EventRecord]:
    """NL -> proposed events (Gemini when API key set; else stub env JSON).

    ``today`` defaults to today's UTC date. ``race_date`` / ``block_weeks`` (from survey
    baseline) ground the Gemini prompt and define the plausibility window for stderr
    date flags on proposed payloads.
    """
    td = today if today is not None else datetime.now(timezone.utc).date()
    window = _date_window(td, race_date, block_weeks)
    force_stub = os.environ.get("Z2TC_DISABLE_GEMINI", "").strip().lower() in ("1", "true", "yes")
    if not force_stub and _gemini_api_key():
        try:
            raw = _gemini_generate_json(
                text, today=td, race_date=race_date, block_weeks=block_weeks
            )
            if raw:
                payloads = _gemini_parse_payloads(raw, break_days=break_days, cross_trained=cross_trained)
                if payloads:
                    recs = [
                        EventRecord(athlete_id=athlete_id, source=source, status="proposed", payload=p)
                        for p in payloads
                    ]
                    recs = _normalize_proposed_records(athlete_id, recs, window)
                    return _apply_date_flags(athlete_id, recs, window)
        except Exception as exc:
            model = _gemini_model_name()
            detail = str(exc).strip().replace("\n", " ")
            if len(detail) > 120:
                detail = detail[:117] + "..."
            tail = f"{exc.__class__.__name__}: {detail}" if detail else exc.__class__.__name__
            print(
                f"Gemini extraction failed (model={model}, {tail}): falling back to stub",
                file=sys.stderr,
            )
    recs = stub_extract_events(
        text, athlete_id=athlete_id, source=source, break_days=break_days, cross_trained=cross_trained
    )
    recs = _normalize_proposed_records(athlete_id, recs, window)
    return _apply_date_flags(athlete_id, recs, window)


# Bump when the personalization prompt below changes in a way that could shift output. Captured on
# every smoothed render (`narrative_renders.prompt_version`) so later analysis can attribute a change
# in LLM behavior to a prompt revision vs a model swap.
NARRATE_PROMPT_VERSION = "p1"


def active_narrate_model() -> str | None:
    """Which model would `narrate_personalization` use right now: ``"stub"`` (test fixture),
    the Gemini model name (live key), or ``None`` (no model → deterministic only). Lets the capture
    layer record provenance without re-deriving the selection logic."""
    if os.environ.get("Z2TC_LLM_STUB_NARRATIVE_JSON", "").strip():
        return "stub"
    return _gemini_model_name() if _gemini_api_key() else None


_PERSONALIZE_SYSTEM = """You are an experienced, warm marathon coach writing to one athlete.
You will receive a JSON object mapping narrative surface names to draft coaching prose, plus
non-numeric grounding signals. Rephrase each surface so it reads as natural, encouraging,
first-person coaching ("I"/"you") with good flow.

HARD RULES:
- Preserve every number EXACTLY as written (paces, mileage, VDOT, times, percentages). Do not add,
  remove, round, or invent any number. If a fact is not in the draft, do not introduce it.
- Keep the same meaning and the same set of facts; you are only improving tone and cohesion.
- Return a JSON object ONLY (no markdown) with the SAME keys you were given, each mapping to the
  rephrased string. Omit nothing."""


def validate_numbers_subset(text: str, allowed: set[str]) -> None:
    """Reject prose that introduces a numeric token not present in ``allowed`` (the numbers the
    deterministic facts legitimately contain). This is what lets the LLM rephrase surfaces that
    legitimately carry paces/mileage without being able to fabricate new figures."""
    from engine.personalization import numbers_in

    extra = numbers_in(text) - set(allowed)
    if extra:
        raise ValueError(f"LLM narrative introduced numbers not in the facts: {sorted(extra)}")


def _stub_narrative() -> dict[str, str] | None:
    raw = os.environ.get("Z2TC_LLM_STUB_NARRATIVE_JSON", "").strip()
    if not raw:
        return None
    data = json.loads(raw)
    return data if isinstance(data, dict) else None


def narrate_personalization(ctx: "PersonalizationContext") -> dict[str, str] | None:
    """Rephrase the plan-sheet paragraph surfaces for tone (number-safe). Returns a surface→prose
    dict, or ``None`` when there is no model available or the number-subset guard rejects any output
    — callers then keep the deterministic prose. Numbers can never be fabricated (see
    :func:`validate_numbers_subset`). ``Z2TC_LLM_STUB_NARRATIVE_JSON`` supplies output in tests."""
    if not getattr(ctx, "surfaces", None):
        return None
    try:
        smoothed = _stub_narrative()
        if smoothed is None:
            if not _gemini_api_key():
                return None
            payload = {"surfaces": ctx.surfaces, "signals": ctx.signals}
            prompt = _PERSONALIZE_SYSTEM + "\n\n" + json.dumps(payload, ensure_ascii=False)
            raw = _gemini_complete_json(prompt)
            if not raw:
                return None
            smoothed = json.loads(_strip_json_fence(raw))
        if not isinstance(smoothed, dict):
            return None
        out: dict[str, str] = {}
        for name, original in ctx.surfaces.items():
            text = smoothed.get(name)
            if not isinstance(text, str) or not text.strip():
                return None  # incomplete rephrase → fall back wholesale (deterministic)
            validate_numbers_subset(text, ctx.allowed_numbers)
            out[name] = text.strip()
        return out
    except (ValueError, json.JSONDecodeError, KeyError, TypeError):
        return None


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
    header_rgb: tuple[float, float, float] | None = None
    tabs = format_dump.get("tabs") or []
    for tab in tabs:
        for cell in tab.get("sample_cells") or []:
            fmt = cell.get("userEnteredFormat") or {}
            t = fmt.get("textFormat") or {}
            bg = fmt.get("backgroundColor") or {}
            if t.get("fontSize") and spec.title_font_size is None:
                spec.title_font_size = int(t["fontSize"])
            if t.get("fontFamily") and spec.title_font_family is None:
                spec.title_font_family = str(t["fontFamily"])
            if bg and t.get("bold") and header_rgb is None:
                header_rgb = (float(bg["red"]), float(bg["green"]), float(bg["blue"]))
    if header_rgb:
        spec.header_rgb = header_rgb
    return spec


def validate_no_numeric_authority(text: str) -> None:
    """Reject strings that look like they assert paces/miles (coarse guard for LLM output)."""
    if re.search(r"\b\d{1,2}:\d{2}\s*/mi\b", text, re.I):
        raise ValueError("LLM output must not include pace numbers")
    if re.search(r"\b\d{2}\.?\d*\s*mpw\b", text, re.I):
        raise ValueError("LLM output must not include mpw numbers")
