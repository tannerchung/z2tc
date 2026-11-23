"""Deterministic classifier & harvester for historical Runna / Strava quality workouts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from engine.narrative_capture import is_default_strava_title


@dataclass(frozen=True)
class HarvestedWorkout:
    activity_id: str
    title: str
    description: str
    detected_source: str          # "Runna" | "Club/Coach" | "Self"
    category: str                 # one of the 7 CatalogWorkout categories
    matched_catalog_key: str | None


@dataclass(frozen=True)
class HarvestReport:
    total_scanned: int
    quality_sessions: tuple[HarvestedWorkout, ...] = ()
    unindexed_candidates: tuple[HarvestedWorkout, ...] = ()
    by_category_counts: dict[str, int] = field(default_factory=dict)


_RULES: tuple[tuple[re.Pattern[str], str, str | None], ...] = (
    (re.compile(r"over\s*/\s*under|alternat", re.I), "lactate_shuttle", "over_unders"),
    (re.compile(r"kenyan\s+hill|continuous\s+.*hill", re.I), "hill_strength", None),
    (re.compile(r"hill\s+(repeat|sprint|rep|session|\d)", re.I), "hill_strength", "hill_repeats"),
    (re.compile(r"drop\s*set", re.I), "vo2max_aerobic_power", "drop_set"),
    (re.compile(r"pyramid", re.I), "vo2max_aerobic_power", "vo2_pyramid"),
    (re.compile(r"descending", re.I), "vo2max_aerobic_power", "descending_i"),
    (re.compile(r"rolling\s*400", re.I), "neuromuscular_speed", "rolling_400s"),
    (re.compile(r"mona\s+fartlek|time[\s-]*based\s+fartlek", re.I), "vo2max_aerobic_power", "mona_fartlek"),
    (re.compile(r"2-1-1|threshold\s+ladder|tempo\s+ladder", re.I), "lactate_threshold", "tempo_ladder"),
    (re.compile(r"broken[\s-]*t|half[\s-]*mile\s+thresh", re.I), "lactate_threshold", "broken_t"),
    (re.compile(r"cruise\s+interval|mile\s+repeat.*thresh", re.I), "lactate_threshold", "cruise_mile"),
    (re.compile(r"\btempo\b", re.I), "lactate_threshold", "tempo"),
    (re.compile(r"block.*long|mp\s+block", re.I), "marathon_specific", "mp_blocks"),
    (re.compile(r"fast[\s-]*finish", re.I), "marathon_specific", "fast_finish"),
    (re.compile(r"progression|progressive", re.I), "marathon_specific", "progression"),
    (re.compile(r"dress\s+rehearsal|race[\s-]*practice", re.I), "marathon_specific", "race_practice"),
    (re.compile(r"1000m|1km\s+rep|1200m|vo2|\d+\s*x\s*1\s*k|\d+\s*x\s*800", re.I), "vo2max_aerobic_power", "vo2_intervals"),
    (re.compile(r"200m|400m|speed\s+rep|\d+\s*x\s*400", re.I), "neuromuscular_speed", "speed_reps"),
)


def classify_historical_workout(activity: dict[str, Any]) -> HarvestedWorkout | None:
    title = str(activity.get("name") or "").strip()
    desc = str(activity.get("description") or activity.get("private_note") or "").strip()
    wtype = activity.get("workout_type")
    if is_default_strava_title(title) and not desc and wtype not in (1, 3):
        return None

    blob = f"{title} {desc}"
    source = "Runna" if "runna" in blob.lower() else ("Club/Coach" if wtype == 3 else "Self")

    for pattern, cat, key in _RULES:
        if pattern.search(blob):
            return HarvestedWorkout(
                activity_id=str(activity.get("id") or ""),
                title=title,
                description=desc,
                detected_source=source,
                category=cat,
                matched_catalog_key=key,
            )

    if wtype == 3 or "runna" in blob.lower():
        return HarvestedWorkout(
            activity_id=str(activity.get("id") or ""),
            title=title,
            description=desc,
            detected_source=source,
            category="unclassified_quality",
            matched_catalog_key=None,
        )
    return None


def harvest_activities(activities: list[dict[str, Any]]) -> HarvestReport:
    quality: list[HarvestedWorkout] = []
    unindexed: list[HarvestedWorkout] = []
    counts: dict[str, int] = {}

    for act in activities:
        hw = classify_historical_workout(act)
        if hw is None:
            continue
        quality.append(hw)
        counts[hw.category] = counts.get(hw.category, 0) + 1
        if hw.matched_catalog_key is None:
            unindexed.append(hw)

    return HarvestReport(
        total_scanned=len(activities),
        quality_sessions=tuple(quality),
        unindexed_candidates=tuple(unindexed),
        by_category_counts=counts,
    )
