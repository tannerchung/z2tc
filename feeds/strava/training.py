"""Reconstruct an athlete's training history week-by-week.

Strava's profile feed does not paginate far back, but the profile "weekly activities"
widget (below the photos reel) fetches one ISO week at a time from:

    /athletes/{id}/interval?interval=YYYYWW&interval_type=week&chart_type=miles&year_offset=N

That endpoint requires AJAX headers and returns a ``text/javascript`` body that injects
the week's date label, totals, and a re-rendered feed whose ``data-react-props`` carries
``preFetchedEntries`` — every activity that week in full detail. We walk a date range one
ISO week at a time and parse each response into structured workouts.
"""

from __future__ import annotations

import dataclasses
import html
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from playwright.sync_api import Page

from .athlete import WorkoutPost, _clean, workouts_from_entry
from .session import BASE_URL

_AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "text/javascript, text/html, application/xml, text/xml, */*",
}


@dataclass
class TrainingWeek:
    iso_year: int
    iso_week: int
    week_start: str  # ISO date (Monday)
    date_label: str | None = None
    total_distance: str | None = None
    total_time: str | None = None
    total_elevation: str | None = None
    workouts: list[WorkoutPost] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _js_unescape(text: str) -> str:
    """Reverse the escaping Strava applies to a JS double-quoted string literal.
    Protect literal backslashes first so ``\\u003c`` survives as ``\\u003c`` for the
    later JSON decode rather than being mangled."""
    return (
        text.replace("\\\\", "\x00")
        .replace('\\"', '"')
        .replace("\\/", "/")
        .replace("\\'", "'")
        .replace("\\$", "$")  # JS escapes literal $ (e.g. ROKA "Earn a \\$50 voucher")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\r", "")
        .replace("\x00", "\\")
    )


# Any backslash not starting a valid JSON escape (" \ / b f n r t u) is a stray JS
# escape Strava left behind; dropping it keeps one odd entry from voiding a whole week.
_INVALID_JSON_ESCAPE = re.compile(r'\\(?![\\"/bfnrtu])')


def _parse_feed_props(js_text: str) -> dict | None:
    """Extract and decode the feed micro-frontend props embedded in the interval JS."""
    match = re.search(r"data-react-props=\\'(.*?)\\'", js_text, re.S)
    if not match:
        return None
    blob = html.unescape(_js_unescape(match.group(1)))
    try:
        return json.loads(blob)
    except (json.JSONDecodeError, ValueError):
        try:
            return json.loads(_INVALID_JSON_ESCAPE.sub("", blob))
        except (json.JSONDecodeError, ValueError):
            return None


def _parse_totals(js_text: str) -> tuple[str | None, str | None, str | None]:
    """Pull the three weekly totals (distance, time, elevation) from #totals."""
    match = re.search(r'#totals"\)\.html\("(.*?)"\);', js_text, re.S)
    if not match:
        return None, None, None
    block = _js_unescape(match.group(1))
    values = [_clean(v) for v in re.findall(r"<strong>(.*?)</strong>", block, re.S)]
    values += [None, None, None]
    return values[0], values[1], values[2]


def _parse_date_label(js_text: str) -> str | None:
    match = re.search(r'#interval-value"\)\.html\("(.*?)"\);', js_text, re.S)
    if not match:
        return None
    return _clean(_js_unescape(match.group(1)))


def parse_interval_response(
    js_text: str, owner_athlete_id: str | None = None
) -> tuple[str | None, tuple, list[WorkoutPost]]:
    """Parse one interval endpoint response into (date_label, totals, workouts)."""
    date_label = _parse_date_label(js_text)
    totals = _parse_totals(js_text)
    props = _parse_feed_props(js_text)
    workouts: list[WorkoutPost] = []
    if props:
        for entry in props.get("appContext", {}).get("preFetchedEntries", []) or []:
            workouts.extend(workouts_from_entry(entry, owner_athlete_id))
    # Chronological within the week (oldest first).
    workouts.sort(key=lambda w: w.start_date or "")
    return date_label, totals, workouts


def iter_iso_weeks(start: date, end: date):
    """Yield unique (iso_year, iso_week, monday_date) from start..end inclusive."""
    seen = set()
    cursor = start
    while cursor <= end:
        iso_year, iso_week, _ = cursor.isocalendar()
        key = (iso_year, iso_week)
        if key not in seen:
            seen.add(key)
            monday = cursor - timedelta(days=cursor.weekday())
            yield iso_year, iso_week, monday
        cursor += timedelta(days=7)


def fetch_week(
    page: Page, athlete_id: str, iso_year: int, iso_week: int, monday: date
) -> TrainingWeek:
    today_year = date.today().year
    interval = iso_year * 100 + iso_week
    year_offset = today_year - iso_year
    url = (
        f"{BASE_URL}/athletes/{athlete_id}/interval"
        f"?interval={interval}&interval_type=week&chart_type=miles"
        f"&year_offset={year_offset}"
    )
    resp = page.request.get(
        url, headers={**_AJAX_HEADERS, "Referer": f"{BASE_URL}/athletes/{athlete_id}"}
    )
    week = TrainingWeek(
        iso_year=iso_year, iso_week=iso_week, week_start=monday.isoformat()
    )
    if resp.status != 200:
        return week
    date_label, totals, workouts = parse_interval_response(
        resp.text(), str(athlete_id)
    )
    week.date_label = date_label
    week.total_distance, week.total_time, week.total_elevation = totals
    week.workouts = workouts
    return week


def scrape_training_history(
    page: Page,
    athlete_id: str,
    start: date,
    end: date,
    *,
    delay_s: float = 1.0,
) -> list[TrainingWeek]:
    """Fetch every ISO week overlapping [start, end] for the athlete."""
    weeks: list[TrainingWeek] = []
    # Anchor the session on the profile so AJAX Referer/cookies look natural.
    page.goto(f"{BASE_URL}/athletes/{athlete_id}", wait_until="domcontentloaded")
    for iso_year, iso_week, monday in iter_iso_weeks(start, end):
        week = fetch_week(page, athlete_id, iso_year, iso_week, monday)
        weeks.append(week)
        if delay_s:
            page.wait_for_timeout(int(delay_s * 1_000))
    return weeks
