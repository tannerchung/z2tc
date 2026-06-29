"""iCalendar (RFC 5545) feed for a training plan.

Emits one all-day VEVENT per session so the schedule is subscribable in Google / Apple / Garmin
Connect calendars. UIDs are stable per (athlete, plan week, day) so re-exporting updates events in
place rather than duplicating them. Pure stdlib.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from engine.plan.models import TrainingPlan
from export.structured import ExportRepeat, ExportWorkout, plan_to_workouts


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 octet-based folding at 75 bytes, continuation lines prefixed with a space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks, start = [], 0
    limit = 75
    while start < len(raw):
        end = min(start + limit, len(raw))
        # Don't split a multibyte char: back off until the next byte is not a continuation byte.
        while end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(raw[start:end].decode("utf-8"))
        start = end
        limit = 74  # continuation lines lose one octet to the leading space
    return "\r\n ".join(chunks)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "athlete"


def _description(ew: ExportWorkout) -> str:
    lines = [ew.description, "", f"Phase: {ew.phase}  ·  Week {ew.week_index}"]
    body: list[str] = []
    for item in ew.steps:
        if isinstance(item, ExportRepeat):
            inner = ", ".join(s.label for s in item.steps)
            body.append(f"{item.count} × ({inner})")
        elif item.intensity != "rest":
            body.append(item.label)
    if len(body) > 1:
        lines += ["", "Steps:"] + [f"  • {b}" for b in body]
    return "\n".join(lines)


def plan_to_ics(
    plan: TrainingPlan,
    *,
    calendar_name: str | None = None,
    now: datetime | None = None,
    running_only: bool = False,
) -> str:
    """Render the plan as an iCalendar string (CRLF line endings)."""
    athlete = plan.athlete or "Athlete"
    cal_name = calendar_name or f"{athlete} — z2tc {plan.method.capitalize()} plan"
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    slug = _slug(athlete)

    out: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//z2tc//plan-export//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(cal_name)}",
    ]
    for ew in plan_to_workouts(plan, running_only=running_only):
        if not ew.date:
            continue
        d = date.fromisoformat(ew.date)
        dtend = d + timedelta(days=1)  # all-day VEVENT end is exclusive
        miles = f"{ew.total_mi:g} mi · " if ew.total_mi else ""
        summary = f"z2tc · {miles}{ew.description}"
        out += [
            "BEGIN:VEVENT",
            f"UID:{slug}-w{ew.week_index}-{ew.day.lower()}-{ew.date}@z2tc",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{dtend.strftime('%Y%m%d')}",
            _fold(f"SUMMARY:{_escape(summary)}"),
            _fold(f"DESCRIPTION:{_escape(_description(ew))}"),
            f"CATEGORIES:{ew.sport.upper()},{ew.phase.upper()}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"
