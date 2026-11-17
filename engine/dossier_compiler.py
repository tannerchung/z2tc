"""Zero-bloat 1Hz stream compactor (<= 2,048 bytes), deterministic athlete dossier
compiler (0 LLM tokens on write), and Strava rate-limit quota guard."""

from __future__ import annotations

import json
from collections import deque
from typing import Any

METERS_PER_MILE = 1609.344
MAX_COMPACT_BYTES = 2048


def compact_1hz_stream_to_summary(
    *,
    activity_id: str,
    velocity_m_s: list[float],
    heartrate_bpm: list[int | float] | None = None,
    cadence_spm: list[int | float] | None = None,
    altitude_m: list[float] | None = None,
) -> dict[str, Any]:
    """Compacts raw 1Hz Garmin/Strava stream arrays in RAM to a <= 2,048-byte summary."""
    n = len(velocity_m_s)
    if n == 0:
        return {
            "activity_id": activity_id,
            "duration_s": 0,
            "distance_mi": 0.0,
            "cardiac_drift_pct": 0.0,
            "mile_splits": [],
        }

    hr = list(heartrate_bpm) if heartrate_bpm and len(heartrate_bpm) == n else []
    cad = list(cadence_spm) if cadence_spm and len(cadence_spm) == n else []
    alt = list(altitude_m) if altitude_m and len(altitude_m) == n else []

    total_m = sum(max(0.0, float(v)) for v in velocity_m_s)
    distance_mi = total_m / METERS_PER_MILE

    # Aerobic decoupling / cardiac drift: compare Efficiency Factor (speed / HR) first half vs second half
    cardiac_drift_pct = 0.0
    if hr and n >= 120:
        mid = n // 2
        v1 = sum(velocity_m_s[:mid]) / mid
        v2 = sum(velocity_m_s[mid:]) / (n - mid)
        hr1 = sum(hr[:mid]) / mid
        hr2 = sum(hr[mid:]) / (n - mid)
        if hr1 > 40 and hr2 > 40 and v1 > 0.5:
            ef1 = v1 / hr1
            ef2 = v2 / hr2
            cardiac_drift_pct = round(((ef1 - ef2) / ef1) * 100.0, 2)

    # Compute per-mile splits [pace_s_per_mi, avg_hr]
    mile_splits: list[list[int]] = []
    acc_m = 0.0
    split_s = 0
    split_hr_sum = 0.0
    for idx, v in enumerate(velocity_m_s):
        acc_m += max(0.0, float(v))
        split_s += 1
        if hr:
            split_hr_sum += float(hr[idx])
        if acc_m >= METERS_PER_MILE:
            avg_split_hr = int(round(split_hr_sum / max(1, split_s))) if hr else 0
            mile_splits.append([split_s, avg_split_hr])
            acc_m -= METERS_PER_MILE
            split_s = 0
            split_hr_sum = 0.0

    elev_gain_ft = 0
    if len(alt) >= 2:
        gain_m = sum(max(0.0, float(alt[i]) - float(alt[i - 1])) for i in range(1, len(alt)))
        elev_gain_ft = int(round(gain_m * 3.28084))

    summary: dict[str, Any] = {
        "activity_id": activity_id,
        "duration_s": n,
        "distance_mi": round(distance_mi, 2),
        "avg_hr": int(round(sum(hr) / len(hr))) if hr else None,
        "max_hr": int(round(max(hr))) if hr else None,
        "avg_cadence_spm": int(round(sum(cad) / len(cad))) if cad else None,
        "elev_gain_ft": elev_gain_ft,
        "cardiac_drift_pct": cardiac_drift_pct,
        "mile_splits": mile_splits[:40],
    }

    # Guarantee hard <= 2,048-byte Postgres CHECK invariant even on 50-100mi ultra activities
    while (
        len(json.dumps(summary, separators=(",", ":")).encode("utf-8")) > MAX_COMPACT_BYTES
        and summary["mile_splits"]
    ):
        summary["mile_splits"] = summary["mile_splits"][:-2]

    return summary


def apply_event_to_dossier(
    *,
    dossier: dict[str, Any],
    event: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Deterministically folds a new athlete event into structured_facts + compiled_truth_md.
    Stages a HITL coach_review_queue card when clinical/GI thresholds fire."""
    facts = dict(dossier.get("structured_facts") or {})
    timeline = list(dossier.get("timeline_log") or [])
    kind = str(event.get("kind") or "Note")
    event_id = str(event.get("event_id") or "")
    occurred_at = str(event.get("occurred_at") or "")

    review_card: dict[str, Any] | None = None

    if kind == "FuelingLog":
        if event.get("preferred_gel"):
            facts["preferred_gel"] = event["preferred_gel"]
        if event.get("carbs_g_per_hr") is not None:
            facts["carbs_g_per_hr"] = float(event["carbs_g_per_hr"])
        gi = int(event.get("gi_distress_1_to_5") or 0)
        facts["last_gi_distress_1_to_5"] = gi
        if gi >= 4:
            review_card = {
                "athlete_id": dossier.get("athlete_id"),
                "trigger_event_id": event_id,
                "status": "pending_coach_review",
                "proposed_action_md": f"High GI distress ({gi}/5) logged; review gut-training carb target.",
            }

    elif kind == "PainFlag":
        loc = str(event.get("location") or "unspecified")
        sev = int(event.get("severity_1_to_5") or 0)
        facts["active_pain_location"] = loc
        facts["active_pain_severity_1_to_5"] = sev
        if sev >= 3:
            review_card = {
                "athlete_id": dossier.get("athlete_id"),
                "trigger_event_id": event_id,
                "status": "pending_coach_review",
                "proposed_action_md": (
                    f"Pain flag ({loc}, severity {sev}/5): hold quality session pending Coach review."
                ),
            }

    timeline.append(
        {
            "event_id": event_id,
            "occurred_at": occurred_at,
            "kind": kind,
            "note": str(event.get("note") or "")[:180],
        }
    )
    timeline = timeline[-50:]

    bullets = [
        f"- **VDOT:** {facts.get('vdot', 'untested')}",
        f"- **Fueling:** {facts.get('preferred_gel', 'untested')} ({facts.get('carbs_g_per_hr', 'n/a')} g/hr)",
    ]
    if facts.get("active_pain_location"):
        bullets.append(
            f"- **Active Watchlist:** {facts['active_pain_location']} ({facts.get('active_pain_severity_1_to_5')}/5)"
        )

    updated = {
        "athlete_id": dossier.get("athlete_id"),
        "structured_facts": facts,
        "compiled_truth_md": "\n".join(bullets),
        "timeline_log": timeline,
    }
    return updated, review_card


class StravaQuotaGuard:
    """Sliding-window rate guard keeping Detour inside Strava's free 200/15m and 2,000/day caps."""

    def __init__(
        self,
        *,
        limit_15m: int = 200,
        buffer_15m: int = 20,
        limit_daily: int = 2000,
        buffer_daily: int = 200,
    ) -> None:
        self.limit_15m = limit_15m
        self.buffer_15m = buffer_15m
        self.limit_daily = limit_daily
        self.buffer_daily = buffer_daily
        self._calls_15m: deque[float] = deque()
        self._calls_daily: deque[float] = deque()

    def _prune(self, now_ts: float) -> None:
        cutoff_15m = now_ts - 900.0
        cutoff_day = now_ts - 86_400.0
        while self._calls_15m and self._calls_15m[0] <= cutoff_15m:
            self._calls_15m.popleft()
        while self._calls_daily and self._calls_daily[0] <= cutoff_day:
            self._calls_daily.popleft()

    def can_execute(self, now_ts: float, *, urgent: bool = False) -> bool:
        self._prune(now_ts)
        cap_15m = self.limit_15m if urgent else (self.limit_15m - self.buffer_15m)
        cap_day = self.limit_daily if urgent else (self.limit_daily - self.buffer_daily)
        return len(self._calls_15m) < cap_15m and len(self._calls_daily) < cap_day

    def record_call(self, now_ts: float) -> None:
        self._prune(now_ts)
        self._calls_15m.append(now_ts)
        self._calls_daily.append(now_ts)
