"""Analytics over a scraped training history (``training.jsonl``).

Produces a per-day calendar, weekly mileage, and best efforts at the standard race
distances. Best times are the fastest *logged run* whose distance is within tolerance
of each benchmark — not Strava's best-effort splits (those live on each activity's
best-efforts page and would require a fetch per run).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .vdot import recommended_vdot

MILES_PER_METER = 1 / 1609.344

# name -> benchmark distance in meters
BENCHMARKS: dict[str, float] = {
    "5K": 5000,
    "10K": 10000,
    "Half Marathon": 21097.5,
    "Marathon": 42195,
}
# Accept runs slightly short to comfortably long (GPS over-reads on races).
_LOWER, _UPPER = 0.96, 1.08

# Word-boundary signals that mark a *title* as a structured workout, not a race
# (e.g. "Marathon pace 8mi", "5k pace x6", "tempo", "threshold"). Matched with \b so
# "pace" does not fire on "pacers" and "rep" does not fire on "prepare".
_WORKOUT_WORDS = (
    "pace",
    "speed",
    "tempo",
    "recovery",
    "interval",
    "intervals",
    "threshold",
    "ladder",
    "fartlek",
    "shakeout",
    "shake-out",
    "splits",
    "rep",
    "reps",
    "workout",
    "progression",
    "warmup",
    "cooldown",
)
# Substring signals (symbols / multi-word phrases that have no clean word boundary).
_WORKOUT_SUBSTR = (
    "warm up",
    "warm-up",
    "cool down",
    "cool-down",
    "shake out",
    "long run",
    "@",
    " x ",
    "x400",
    "x800",
    "x200",
    "x1000",
    "x1200",
)
_WORKOUT_WORD_RE = re.compile(r"\b(?:" + "|".join(_WORKOUT_WORDS) + r")\b")

# A logged run must be within tolerance of the official distance to count as that
# race (guards against a 3-mi "marathon shakeout" or a mislabelled note).
_RACE_DISTANCE_MI = {"5K": 3.107, "10K": 6.214, "Half Marathon": 13.109, "Marathon": 26.219}
_DIST_LOWER, _DIST_UPPER = 0.85, 1.15


def _has_workout_signal(text: str) -> bool:
    return bool(_WORKOUT_WORD_RE.search(text)) or any(s in text for s in _WORKOUT_SUBSTR)


def _race_distance_category(text: str) -> str | None:
    """Map race text to a distance label. Order matters: 'half marathon'/'half'
    before 'marathon', and explicit 'NNk' last."""
    if "half marathon" in text or re.search(r"\bhalf\b", text):
        return "Half Marathon"
    if re.search(r"\bmarathon\b", text):
        return "Marathon"
    match = re.search(r"\b(\d{1,2})\s?k\b", text)
    if match and int(match.group(1)) in (5, 10):
        return f"{int(match.group(1))}K"
    return None


def detect_race(
    name: str | None, description: str | None = None, miles: float | None = None
) -> str | None:
    """Classify an activity as a race from its *title* and return the distance category
    (e.g. 'NYC Marathon' -> Marathon, 'Brooklyn Half' -> Half Marathon). Detection is
    title-driven: a clear race title wins regardless of the recap notes. Titles that
    are really workouts ('Marathon pace 8mi', '5k pace x6') are rejected, and when the
    logged distance is known it must be within tolerance of the named race distance.

    ``description`` is accepted for backwards compatibility but no longer used to
    classify (recaps mention distances and pace words too freely to trust)."""
    title = (name or "").lower()
    if _has_workout_signal(title):
        return None
    cat = _race_distance_category(title)
    if not cat:
        return None
    ref = _RACE_DISTANCE_MI.get(cat)
    if miles is not None and ref is not None:
        if not (_DIST_LOWER * ref <= miles <= _DIST_UPPER * ref):
            return None
    return cat


def official_time_s(description: str | None) -> int | None:
    """Pull a chip/official finish time out of a race recap when present
    (e.g. 'Official time: 03:50:13'). The weekly feed only carries minute precision,
    so this recovers exact seconds for a more accurate VDOT."""
    if not description:
        return None
    match = re.search(
        r"(?:official|chip|finish(?:ing)?|gun)\s*time[:\s]*"
        r"(\d{1,2}):(\d{2}):(\d{2})",
        description,
        re.IGNORECASE,
    )
    if not match:
        return None
    h, m, s = (int(g) for g in match.groups())
    return h * 3600 + m * 60 + s


def parse_miles(stat: str | None) -> float | None:
    if not stat:
        return None
    match = re.search(r"([\d.]+)\s*mi", stat)
    return float(match.group(1)) if match else None


def parse_duration_s(stat: str | None) -> int | None:
    """Parse a Strava 'Time' stat like '1h 27m', '30m 8s', '53m 23s' to seconds."""
    if not stat:
        return None
    total = 0
    for value, unit in re.findall(r"(\d+)\s*([hms])", stat):
        total += int(value) * {"h": 3600, "m": 60, "s": 1}[unit]
    return total or None


def fmt_duration(seconds: int | None) -> str:
    if not seconds:
        return "-"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@dataclass
class RunStat:
    date: str
    name: str | None
    miles: float | None
    duration_s: int | None
    pace: str | None
    url: str | None
    race_category: str | None = None


@dataclass
class TrainingSummary:
    weeks: int
    total_activities: int
    total_runs: int
    total_run_miles: float
    weekly_run_miles: dict[str, float] = field(default_factory=dict)
    longest_run: dict | None = None
    bests: dict[str, dict] = field(default_factory=dict)
    races: list[dict] = field(default_factory=list)
    best_races: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "weeks": self.weeks,
            "total_activities": self.total_activities,
            "total_runs": self.total_runs,
            "total_run_miles": round(self.total_run_miles, 1),
            "weekly_run_miles": {k: round(v, 1) for k, v in self.weekly_run_miles.items()},
            "longest_run": self.longest_run,
            "bests": self.bests,
            "races": self.races,
            "best_races": self.best_races,
        }


def load_weeks(path: Path | str) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run_stats(weeks: list[dict]) -> list[RunStat]:
    runs: list[RunStat] = []
    for week in weeks:
        for w in week.get("workouts", []):
            if (w.get("sport_type") or "") != "Run":
                continue
            stats = w.get("stats", {}) or {}
            miles = parse_miles(stats.get("Distance"))
            category = detect_race(w.get("name"), w.get("description"), miles)
            duration = parse_duration_s(stats.get("Time")) or w.get("elapsed_time_s")
            # For races, a chip time in the notes beats the minute-rounded feed time.
            if category:
                duration = official_time_s(w.get("description")) or duration
            runs.append(
                RunStat(
                    date=(w.get("start_date") or "")[:10],
                    name=w.get("name"),
                    miles=miles,
                    duration_s=duration,
                    pace=stats.get("Pace"),
                    url=w.get("url"),
                    race_category=category,
                )
            )
    return runs


def build_calendar(weeks: list[dict]) -> dict[str, list[dict]]:
    """Map ISO date -> list of activities that day (chronological)."""
    calendar: dict[str, list[dict]] = {}
    for week in weeks:
        for w in week.get("workouts", []):
            day = (w.get("start_date") or "")[:10]
            if not day:
                continue
            stats = w.get("stats", {}) or {}
            calendar.setdefault(day, []).append(
                {
                    "type": w.get("sport_type"),
                    "name": w.get("name"),
                    "distance": stats.get("Distance"),
                    "pace": stats.get("Pace"),
                    "time": stats.get("Time"),
                    "url": w.get("url"),
                }
            )
    return dict(sorted(calendar.items()))


def _best_at_distance(runs: list[RunStat], meters: float) -> dict | None:
    target_mi = meters * MILES_PER_METER
    candidates = [
        r
        for r in runs
        if r.miles
        and r.duration_s
        and _LOWER * target_mi <= r.miles <= _UPPER * target_mi
    ]
    if not candidates:
        return None
    best = min(candidates, key=lambda r: r.duration_s)
    return {
        "time": fmt_duration(best.duration_s),
        "duration_s": best.duration_s,
        "date": best.date,
        "name": best.name,
        "distance_mi": best.miles,
        "pace": best.pace,
        "url": best.url,
    }


def summarize(weeks: list[dict]) -> TrainingSummary:
    runs = _run_stats(weeks)
    weekly: dict[str, float] = {}
    for week in weeks:
        miles = sum(
            parse_miles((w.get("stats") or {}).get("Distance")) or 0
            for w in week.get("workouts", [])
            if (w.get("sport_type") or "") == "Run"
        )
        weekly[week.get("week_start", "?")] = miles

    longest = max(
        (r for r in runs if r.miles), key=lambda r: r.miles, default=None
    )
    longest_run = (
        {
            "miles": longest.miles,
            "time": fmt_duration(longest.duration_s),
            "date": longest.date,
            "name": longest.name,
            "pace": longest.pace,
            "url": longest.url,
        }
        if longest
        else None
    )

    race_runs = [r for r in runs if r.race_category]
    races = [
        {
            "category": r.race_category,
            "date": r.date,
            "name": r.name,
            "distance_mi": r.miles,
            "time": fmt_duration(r.duration_s),
            "duration_s": r.duration_s,
            "pace": r.pace,
            "url": r.url,
        }
        for r in sorted(race_runs, key=lambda r: r.date)
    ]
    best_races: dict[str, dict] = {}
    for r in race_runs:
        if not r.duration_s:
            continue
        cur = best_races.get(r.race_category)
        if cur is None or r.duration_s < cur["duration_s"]:
            best_races[r.race_category] = {
                "time": fmt_duration(r.duration_s),
                "duration_s": r.duration_s,
                "date": r.date,
                "name": r.name,
                "distance_mi": r.miles,
                "pace": r.pace,
                "url": r.url,
            }

    return TrainingSummary(
        weeks=len(weeks),
        total_activities=sum(len(w.get("workouts", [])) for w in weeks),
        total_runs=len(runs),
        total_run_miles=sum(r.miles for r in runs if r.miles),
        weekly_run_miles=weekly,
        longest_run=longest_run,
        bests={
            name: best
            for name, meters in BENCHMARKS.items()
            if (best := _best_at_distance(runs, meters))
        },
        races=races,
        best_races=best_races,
    )


# --- Marathon training-block report ------------------------------------------


def _filter_weeks(weeks: list[dict], start: date, end: date) -> list[dict]:
    out = []
    for w in weeks:
        try:
            ws = date.fromisoformat(w.get("week_start", ""))
        except ValueError:
            continue
        if start <= ws <= end:
            out.append(w)
    return out


def _pace_to_seconds(pace: str | None) -> int | None:
    """Parse a Strava pace like '8:30 /mi' to seconds per mile."""
    if not pace:
        return None
    match = re.search(r"(\d+):(\d{2})", pace)
    return int(match.group(1)) * 60 + int(match.group(2)) if match else None


def _median_pace(runs: list[RunStat]) -> str | None:
    secs = sorted(s for r in runs if (s := _pace_to_seconds(r.pace)))
    if not secs:
        return None
    mid = secs[len(secs) // 2]
    m, s = divmod(mid, 60)
    return f"{m}:{s:02d} /mi"


def build_marathon_report(
    weeks: list[dict],
    *,
    name: str | None,
    athlete_id: str,
    today: date | None = None,
    block_weeks: int = 20,
) -> dict:
    """Auto-detect the latest marathon, split the data into a training block and a
    post-marathon window, and assemble paces, races, and a VDOT-based plan."""
    today = today or date.today()
    summary = summarize(weeks)
    marathons = [r for r in summary.races if r.get("category") == "Marathon"]
    marathons.sort(key=lambda r: r.get("date") or "")
    latest = marathons[-1] if marathons else None

    report: dict = {
        "athlete_id": athlete_id,
        "name": name,
        "all_marathons_detected": marathons,
        "latest_marathon": latest,
    }

    if not latest:
        report["note"] = "No marathon detected in the scanned range."
        report["all_races_detected"] = summary.races
        report["recommended_vdot"] = recommended_vdot(summary.races)
        return report

    m_date = date.fromisoformat(latest["date"])
    block_start = m_date - timedelta(weeks=block_weeks)
    block_weeks_data = _filter_weeks(weeks, block_start, m_date)
    post_weeks_data = _filter_weeks(weeks, m_date + timedelta(days=1), today)

    block_summary = summarize(block_weeks_data)
    block_runs = _run_stats(block_weeks_data)
    post_summary = summarize(post_weeks_data)

    # VDOT from the most appropriate race: prefer post-marathon races (current
    # fitness), then fall back to races during/before the block.
    vdot = recommended_vdot(post_summary.races) or recommended_vdot(summary.races)

    report["training_block"] = {
        "start": block_start.isoformat(),
        "end": m_date.isoformat(),
        "weeks": len(block_weeks_data),
        "total_run_miles": round(block_summary.total_run_miles, 1),
        "weekly_run_miles": {
            k: round(v, 1) for k, v in block_summary.weekly_run_miles.items()
        },
        "peak_week": max(
            block_summary.weekly_run_miles.items(),
            key=lambda kv: kv[1],
            default=(None, 0),
        )[0],
        "longest_run": block_summary.longest_run,
        "median_pace": _median_pace(block_runs),
        "calendar": build_calendar(block_weeks_data),
    }
    report["post_marathon"] = {
        "from": (m_date + timedelta(days=1)).isoformat(),
        "to": today.isoformat(),
        "races": post_summary.races,
        "best_races": post_summary.best_races,
    }
    report["all_races_detected"] = summary.races
    report["recommended_vdot"] = vdot
    return report
