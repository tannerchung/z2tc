"""Unit tests for ``llm.boundary`` parsing helpers and Gemini JSON coercion (no network)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Union, get_args, get_origin

import pytest
from pydantic import BaseModel

from engine.vdot import RACE_METERS
from llm.boundary import (
    _build_grounding,
    _date_in_window,
    _date_window,
    _dict_to_payload,
    _payload_date_fields,
    date_window,
    normalize_payload_calendar_dates,
    payload_out_of_window_fields,
    _gemini_model_name,
    _gemini_parse_payloads,
    _normalize_distance_m,
    _parse_hms_to_seconds,
    _strip_json_fence,
    extract_events,
)
from store.events import (
    EventPayload,
    RaceEstimatePayload,
    SetRaceDatePayload,
    UnavailablePayload,
    WeeklyEvaluationPayload,
    parse_event_payload,
)


def test_normalize_distance_m() -> None:
    assert _normalize_distance_m({"distance_m": 5000}) == 5000.0
    assert _normalize_distance_m({"distance": "half"}) == RACE_METERS["Half Marathon"]
    assert _normalize_distance_m({"race_distance": "marathon"}) == RACE_METERS["Marathon"]
    assert _normalize_distance_m({"distance": "unknown_race"}) is None


def test_parse_hms_to_seconds() -> None:
    assert _parse_hms_to_seconds("3:55:00") == 3 * 3600 + 55 * 60
    assert _parse_hms_to_seconds("40:00") == 40 * 60
    assert _parse_hms_to_seconds("") is None
    assert _parse_hms_to_seconds("not-a-time") is None


def test_strip_json_fence() -> None:
    raw = '```json\n[{"kind":"WeeklyEvaluation","week_start":"2026-06-01"}]\n```'
    stripped = _strip_json_fence(raw)
    assert stripped.startswith("[")
    assert "```" not in stripped


def test_gemini_parse_payloads_dict_and_filters_bad_items() -> None:
    one = json.dumps(
        {
            "kind": "WeeklyEvaluation",
            "week_start": "2026-06-01",
            "note": "ok",
        }
    )
    out1 = _gemini_parse_payloads(one, break_days=0, cross_trained=False)
    assert len(out1) == 1
    assert isinstance(out1[0], WeeklyEvaluationPayload)
    assert out1[0].kind == "WeeklyEvaluation"

    mixed = json.dumps(
        [
            1,
            "bad",
            {
                "kind": "WeeklyEvaluation",
                "week_start": "2026-06-08",
                "note": "second",
            },
        ]
    )
    out2 = _gemini_parse_payloads(mixed, break_days=0, cross_trained=False)
    assert len(out2) == 1
    assert isinstance(out2[0], WeeklyEvaluationPayload)
    assert out2[0].week_start == "2026-06-08"


def test_dict_to_payload_race_estimate_label_and_hms() -> None:
    p = _dict_to_payload(
        {
            "kind": "RaceEstimate",
            "race_name": "Test Marathon",
            "race_date": "2025-10-12",
            "distance": "marathon",
            "estimated_time_s": "3:55:00",
            "note": "sick but ~3:55 effort",
        },
        break_days=14,
        cross_trained=False,
    )
    assert isinstance(p, RaceEstimatePayload)
    assert p.distance_m == RACE_METERS["Marathon"]
    assert p.estimated_time_s == 3 * 3600 + 55 * 60
    assert p.estimated_vdot > 0
    assert p.effective_vdot <= p.estimated_vdot


def test_dict_to_payload_race_actual_time_string() -> None:
    p = _dict_to_payload(
        {
            "kind": "RaceEstimate",
            "race_name": "Half",
            "race_date": "2025-01-01",
            "distance": "half",
            "estimated_time_s": "1:30:00",
            "actual_time_s": "1:32:00",
        },
        break_days=0,
        cross_trained=False,
    )
    assert isinstance(p, RaceEstimatePayload)
    assert p.distance_m == RACE_METERS["Half Marathon"]
    assert p.actual_time_s == 92 * 60


def test_extract_events_gemini_empty_json_falls_back_to_stub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("Z2TC_DISABLE_GEMINI", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr("llm.boundary._gemini_api_key", lambda: "fake-key-for-test")
    monkeypatch.setattr("llm.boundary._gemini_generate_json", lambda _t, **_: "[]")
    monkeypatch.setenv(
        "Z2TC_LLM_STUB_EVENTS_JSON",
        json.dumps([{"kind": "WeeklyEvaluation", "week_start": "2026-06-01", "note": "stub"}]),
    )
    recs = extract_events(
        "coach text",
        athlete_id="a99",
        break_days=0,
        cross_trained=False,
        today=date(2026, 6, 1),
        race_date="2026-10-10",
        block_weeks=18,
    )
    assert len(recs) == 1
    assert recs[0].status == "proposed"
    assert recs[0].payload.kind == "WeeklyEvaluation"


def test_gemini_model_name_defaults_to_3_5_flash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("Z2TC_GEMINI_MODEL", raising=False)
    assert _gemini_model_name() == "gemini-3.5-flash"


def test_extract_events_gemini_raises_falls_back_to_stub_with_warning(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("Z2TC_DISABLE_GEMINI", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("Z2TC_GEMINI_MODEL", raising=False)
    monkeypatch.setattr("llm.boundary._gemini_api_key", lambda: "fake-key")

    def _boom(_t: str, **_: object) -> str:
        raise RuntimeError("NOT_FOUND: model unavailable")

    monkeypatch.setattr("llm.boundary._gemini_generate_json", _boom)
    monkeypatch.setenv(
        "Z2TC_LLM_STUB_EVENTS_JSON",
        json.dumps([{"kind": "Difficulty", "delta": -1}]),
    )
    recs = extract_events("x", athlete_id="a1", break_days=0, cross_trained=False)
    assert len(recs) == 1
    assert recs[0].payload.kind == "Difficulty"
    err = capsys.readouterr().err
    assert "Gemini extraction failed" in err
    assert "gemini-3.5-flash" in err
    assert "NOT_FOUND" in err
    assert "falling back to stub" in err


def test_extract_events_gemini_raises_no_stub_returns_empty_with_warning(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("Z2TC_DISABLE_GEMINI", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("Z2TC_LLM_STUB_EVENTS_JSON", raising=False)
    monkeypatch.setattr("llm.boundary._gemini_api_key", lambda: "fake-key")
    def _net_err(_t: str, **_: object) -> str:
        raise OSError("network reset")

    monkeypatch.setattr("llm.boundary._gemini_generate_json", _net_err)
    recs = extract_events("x", athlete_id="a2", break_days=0, cross_trained=False)
    assert recs == []
    err = capsys.readouterr().err
    assert "Gemini extraction failed" in err
    assert "falling back to stub" in err


def test_date_window_with_race() -> None:
    td = date(2026, 6, 1)
    lo, hi = _date_window(td, "2026-10-10", 18)
    span = 18 * 7 + 14
    assert lo == date(2026, 10, 10) - timedelta(days=span)
    assert hi == date(2026, 10, 10) + timedelta(days=14)


def test_date_window_fallback_no_race() -> None:
    td = date(2025, 1, 1)
    lo, hi = _date_window(td, None, None)
    assert lo == td - timedelta(days=365)
    assert hi == td + timedelta(days=365)


def test_date_in_window() -> None:
    w = (date(2026, 5, 23), date(2026, 10, 24))
    assert _date_in_window("2026-06-15", w) is True
    assert _date_in_window("2020-01-01", w) is False
    assert _date_in_window("not-a-date", w) is None


def test_date_window_matches_private_wrapper() -> None:
    td = date(2026, 6, 1)
    assert date_window(td, "2026-10-10", 18) == _date_window(td, "2026-10-10", 18)


def test_payload_out_of_window_fields_weekly() -> None:
    td = date(2026, 6, 1)
    w = date_window(td, "2026-10-10", 18)
    p_in = WeeklyEvaluationPayload(week_start="2026-06-01", note="")
    assert payload_out_of_window_fields(p_in, w) == []
    p_out = WeeklyEvaluationPayload(week_start="2020-01-06", note="")
    assert payload_out_of_window_fields(p_out, w) == [("week_start", "2020-01-06")]


def test_payload_out_of_window_fields_unparseable_ignored() -> None:
    td = date(2026, 6, 1)
    w = date_window(td, "2026-10-10", 18)
    p = WeeklyEvaluationPayload(week_start="not-iso", note="")
    assert payload_out_of_window_fields(p, w) == []


def test_payload_out_of_window_fields_set_race_date_and_unavailable() -> None:
    td = date(2026, 6, 1)
    w = date_window(td, "2026-10-10", 18)
    bad_race = SetRaceDatePayload(race_date="2020-01-06")
    assert payload_out_of_window_fields(bad_race, w) == [("race_date", "2020-01-06")]
    ok_race = SetRaceDatePayload(race_date="2026-10-10")
    assert payload_out_of_window_fields(ok_race, w) == []

    bad_un = UnavailablePayload(start="2020-01-01", end="2020-01-08")
    oow = payload_out_of_window_fields(bad_un, w)
    assert ("start", "2020-01-01") in oow
    assert ("end", "2020-01-08") in oow
    assert len(oow) == 2

    ok_un = UnavailablePayload(start="2026-06-01", end="2026-06-07")
    assert payload_out_of_window_fields(ok_un, w) == []

    bad_parse = UnavailablePayload(start="not-iso", end="2020-01-08")
    assert payload_out_of_window_fields(bad_parse, w) == [("end", "2020-01-08")]


def test_normalize_payload_calendar_dates_weekly_out_of_window_snaps_to_monday_in_window() -> None:
    td = date(2026, 6, 1)
    w = date_window(td, "2026-10-10", 18)
    p = WeeklyEvaluationPayload(week_start="2020-01-06", note="")
    new_p, did = normalize_payload_calendar_dates(p, w)
    assert did is True
    ws = date.fromisoformat(new_p.week_start[:10])
    assert ws.weekday() == 0
    lo, hi = w
    assert lo <= ws <= hi
    assert payload_out_of_window_fields(new_p, w) == []


def test_normalize_payload_calendar_dates_set_race_clamps_to_window() -> None:
    td = date(2026, 6, 1)
    w = date_window(td, "2026-10-10", 18)
    p = SetRaceDatePayload(race_date="2020-01-06")
    new_p, did = normalize_payload_calendar_dates(p, w)
    assert did is True
    rd = date.fromisoformat(new_p.race_date[:10])
    lo, hi = w
    assert lo <= rd <= hi
    assert payload_out_of_window_fields(new_p, w) == []


def test_normalize_payload_calendar_dates_unavailable_repairs_inverted_range() -> None:
    td = date(2026, 6, 1)
    w = date_window(td, "2026-10-10", 18)
    p = UnavailablePayload(start="2020-12-20", end="2020-12-10")
    new_p, did = normalize_payload_calendar_dates(p, w)
    assert did is True
    us = date.fromisoformat(new_p.start[:10])
    ue = date.fromisoformat(new_p.end[:10])
    assert us <= ue


def _event_payload_union_model_classes() -> tuple[type[BaseModel], ...]:
    ann_root = get_args(EventPayload)[0]
    assert get_origin(ann_root) is Union
    return get_args(ann_root)


def _date_like_field_name(name: str) -> bool:
    return name in ("week_start", "race_date", "start", "end") or name.endswith("_date") or name.endswith(
        "_start"
    )


def _annotation_accepts_str(annotation: object) -> bool:
    if annotation is str:
        return True
    origin = get_origin(annotation)
    if origin is Union:
        return any(_annotation_accepts_str(a) for a in get_args(annotation))
    return False


def _model_date_like_str_field_names(model_cls: type[BaseModel]) -> frozenset[str]:
    out: set[str] = set()
    for fname, finfo in model_cls.model_fields.items():
        if fname == "kind":
            continue
        if not _date_like_field_name(fname):
            continue
        if not _annotation_accepts_str(finfo.annotation):
            continue
        out.add(fname)
    return frozenset(out)


def _literal_kind_default(model_cls: type[BaseModel]) -> str:
    default = model_cls.model_fields["kind"].default
    if not isinstance(default, str):
        raise AssertionError(f"{model_cls.__name__}: expected str kind default, got {default!r}")
    return default


def test_event_payload_date_like_fields_are_grounded_or_trusted() -> None:
    """Fail when a new date-like str field is added without updating ``_payload_date_fields``."""
    grounded_kinds = frozenset(
        {
            "WeeklyEvaluation",
            "RaceEstimate",
            "EffortQuality",
            "DataExclude",
            "FitnessAnchor",
            "SetRaceDate",
            "Unavailable",
        }
    )
    trusted_kinds = frozenset({"AdherenceFlag", "EasyPaceDrift", "FatigueFlag", "OverreachFlag"})
    assert not (grounded_kinds & trusted_kinds)

    grounded_samples: dict[str, dict] = {
        "WeeklyEvaluation": {"kind": "WeeklyEvaluation", "week_start": "2026-06-01"},
        "RaceEstimate": {
            "kind": "RaceEstimate",
            "race_name": "M",
            "race_date": "2026-10-10",
            "distance_m": 42195.0,
            "actual_time_s": None,
            "estimated_time_s": 4 * 3600,
            "estimated_vdot": 40.0,
            "effective_vdot": 40.0,
            "break_days": 0,
            "note": "",
        },
        "EffortQuality": {"kind": "EffortQuality", "race_date": "2026-10-10", "quality": "max", "note": ""},
        "DataExclude": {"kind": "DataExclude", "race_date": "2026-10-10", "reason": ""},
        "FitnessAnchor": {
            "kind": "FitnessAnchor",
            "race_date": "2026-10-10",
            "vdot": None,
            "source": "",
            "note": "",
        },
        "SetRaceDate": {"kind": "SetRaceDate", "race_date": "2026-10-10"},
        "Unavailable": {"kind": "Unavailable", "start": "2026-06-01", "end": "2026-06-07", "reason": ""},
    }
    trusted_samples: dict[str, dict] = {
        "AdherenceFlag": {
            "kind": "AdherenceFlag",
            "week_start": "2026-06-01",
            "prescribed_mi": 40.0,
            "actual_mi": 30.0,
            "ratio": 0.75,
        },
        "EasyPaceDrift": {"kind": "EasyPaceDrift", "week_start": "2026-06-01", "drift_s_per_mi": 12.0},
        "FatigueFlag": {"kind": "FatigueFlag", "week_start": "2026-06-01", "reason": "x"},
        "OverreachFlag": {"kind": "OverreachFlag", "week_start": "2026-06-01", "reason": "x"},
    }

    for model_cls in _event_payload_union_model_classes():
        schema_dates = _model_date_like_str_field_names(model_cls)
        if not schema_dates:
            continue
        kind = _literal_kind_default(model_cls)
        assert kind in grounded_kinds or kind in trusted_kinds, (
            f"{model_cls.__name__} ({kind}) has date-like str fields {sorted(schema_dates)} "
            "but is not listed as GROUNDED or TRUSTED_CODE_GENERATED — update llm/boundary._payload_date_fields "
            "and this test."
        )
        assert (kind in grounded_kinds) ^ (kind in trusted_kinds), f"{kind} must be exactly one of grounded/trusted"
        if kind in trusted_kinds:
            payload = parse_event_payload(trusted_samples[kind])
            assert _payload_date_fields(payload) == [], f"{kind} is trusted code-generated; must not ground dates"
        else:
            payload = parse_event_payload(grounded_samples[kind])
            covered = {n for n, _ in _payload_date_fields(payload)}
            missing = schema_dates - covered
            assert not missing, f"{kind}: _payload_date_fields misses schema date fields {sorted(missing)}"


def test_build_grounding_with_race() -> None:
    g = _build_grounding(date(2026, 6, 1), "2026-10-10", 18)
    assert "2026-06-01" in g
    assert "2026-10-10" in g
    assert "2026-05-23" in g
    assert "2026-10-24" in g


def test_build_grounding_no_race() -> None:
    td = date(2025, 1, 1)
    g = _build_grounding(td, None, None)
    assert "2025-01-01" in g
    lo, hi = _date_window(td, None, None)
    assert lo.isoformat() in g
    assert hi.isoformat() in g


def test_extract_events_stub_normalizes_out_of_window_week_start(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.setenv(
        "Z2TC_LLM_STUB_EVENTS_JSON",
        json.dumps([{"kind": "WeeklyEvaluation", "week_start": "2020-01-06", "note": "old"}]),
    )
    recs = extract_events(
        "x",
        athlete_id="af",
        break_days=0,
        cross_trained=False,
        today=date(2026, 6, 1),
        race_date="2026-10-10",
        block_weeks=18,
    )
    assert len(recs) == 1
    err = capsys.readouterr().err
    assert "Date normalized" in err
    assert "2020-01-06" in err
    assert "Date flag" not in err
    p = recs[0].payload
    assert isinstance(p, WeeklyEvaluationPayload)
    ws = date.fromisoformat(p.week_start[:10])
    assert ws.weekday() == 0
    w = date_window(date(2026, 6, 1), "2026-10-10", 18)
    assert w[0] <= ws <= w[1]


def test_extract_events_stub_normalizes_out_of_window_set_race_date(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.setenv(
        "Z2TC_LLM_STUB_EVENTS_JSON",
        json.dumps([{"kind": "SetRaceDate", "race_date": "2020-01-06"}]),
    )
    recs = extract_events(
        "x",
        athlete_id="sr1",
        break_days=0,
        cross_trained=False,
        today=date(2026, 6, 1),
        race_date="2026-10-10",
        block_weeks=18,
    )
    assert len(recs) == 1
    err = capsys.readouterr().err
    assert "Date normalized" in err
    assert "Date flag" not in err
    p = recs[0].payload
    assert isinstance(p, SetRaceDatePayload)
    rd = date.fromisoformat(p.race_date[:10])
    w = date_window(date(2026, 6, 1), "2026-10-10", 18)
    assert w[0] <= rd <= w[1]


def test_extract_events_stub_no_flag_in_window_week_start(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("Z2TC_DISABLE_GEMINI", "1")
    monkeypatch.setenv(
        "Z2TC_LLM_STUB_EVENTS_JSON",
        json.dumps([{"kind": "WeeklyEvaluation", "week_start": "2026-06-01", "note": "ok"}]),
    )
    extract_events(
        "x",
        athlete_id="ok",
        break_days=0,
        cross_trained=False,
        today=date(2026, 6, 1),
        race_date="2026-10-10",
        block_weeks=18,
    )
    assert "Date flag" not in capsys.readouterr().err
