"""Tests for <=2KB 1Hz stream compaction, deterministic dossier compilation, and Strava quota guard."""

from __future__ import annotations

import json

from engine.dossier_compiler import (
    StravaQuotaGuard,
    apply_event_to_dossier,
    compact_1hz_stream_to_summary,
)


def test_1hz_stream_compacts_under_2048_bytes_with_cardiac_drift() -> None:
    # Simulate 3,600 seconds (1 hour) of 1 Hz telemetry (~130 KB raw JSON)
    seconds = 3600
    # Steady 3.35 m/s (~8:00/mi), HR drifting from 145 bpm in first half to 158 bpm in second half
    velocity_m_s = [3.35] * seconds
    heartrate_bpm = [145 + int(13 * (i / seconds)) for i in range(seconds)]
    cadence_spm = [176] * seconds
    altitude_m = [15.0 + (i % 60) * 0.1 for i in range(seconds)]

    raw_payload_bytes = len(
        json.dumps(
            {
                "velocity_smooth": velocity_m_s,
                "heartrate": heartrate_bpm,
                "cadence": cadence_spm,
                "altitude": altitude_m,
            }
        ).encode("utf-8")
    )
    assert raw_payload_bytes > 50_000

    summary = compact_1hz_stream_to_summary(
        activity_id="strava-9918273",
        velocity_m_s=velocity_m_s,
        heartrate_bpm=heartrate_bpm,
        cadence_spm=cadence_spm,
        altitude_m=altitude_m,
    )
    encoded = json.dumps(summary, separators=(",", ":")).encode("utf-8")

    assert len(encoded) <= 2048, f"Compacted JSON exceeded 2KB cap: {len(encoded)} bytes"
    assert "velocity_smooth" not in summary
    assert summary["duration_s"] == 3600
    assert summary["distance_mi"] > 7.4
    assert summary["cardiac_drift_pct"] > 3.5
    assert len(summary["mile_splits"]) >= 7


def test_deterministic_dossier_fold_and_hitl_review_staging() -> None:
    initial = {
        "athlete_id": "athlete-a",
        "structured_facts": {"vdot": 48.0, "preferred_gel": "Untested"},
        "compiled_truth_md": "",
        "timeline_log": [],
    }

    updated, review_item = apply_event_to_dossier(
        dossier=initial,
        event={
            "event_id": "ev-fuel-1",
            "occurred_at": "2026-11-15T14:00:00Z",
            "kind": "FuelingLog",
            "preferred_gel": "Maurten Gel 100",
            "carbs_g_per_hr": 65.0,
            "gi_distress_1_to_5": 1,
            "note": "Stomach settled well on 16-miler.",
        },
    )
    assert review_item is None
    assert updated["structured_facts"]["preferred_gel"] == "Maurten Gel 100"
    assert "Maurten Gel 100" in updated["compiled_truth_md"]
    assert len(updated["timeline_log"]) == 1
    assert updated["timeline_log"][0]["event_id"] == "ev-fuel-1"

    # Pain severity >= 3 stages a Coach Review HITL card without auto-mutating prescribed workouts
    updated_pain, review_pain = apply_event_to_dossier(
        dossier=updated,
        event={
            "event_id": "ev-pain-2",
            "occurred_at": "2026-11-16T13:00:00Z",
            "kind": "PainFlag",
            "location": "right_achilles",
            "severity_1_to_5": 4,
            "note": "Sharp pull on mile 4 of shakeout.",
        },
    )
    assert review_pain is not None
    assert review_pain["status"] == "pending_coach_review"
    assert review_pain["trigger_event_id"] == "ev-pain-2"
    assert updated_pain["structured_facts"]["active_pain_location"] == "right_achilles"


def test_strava_quota_guard_respects_15m_and_daily_buffers() -> None:
    guard = StravaQuotaGuard(limit_15m=200, buffer_15m=20, limit_daily=2000, buffer_daily=200)
    now = 1_763_300_000.0

    for i in range(180):
        assert guard.can_execute(now + i, urgent=False) is True
        guard.record_call(now + i)

    # Non-urgent backfill pauses at 180/200 (20-call reserve preserved for live athlete webhooks)
    assert guard.can_execute(now + 181, urgent=False) is False
    # Live urgent athlete webhook can still use reserve up to hard cap
    assert guard.can_execute(now + 181, urgent=True) is True

    # After 15-minute window rolls over, non-urgent calls resume
    assert guard.can_execute(now + 905 + 180, urgent=False) is True
