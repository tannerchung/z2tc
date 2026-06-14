"""Scrape a Strava athlete profile page into a structured record.

Strava ships the profile activity feed as a React micro-frontend that embeds every
post as JSON in a ``data-react-props`` attribute (``preFetchedEntries``). We parse
that JSON for workout posts — it is far more stable and richer than the rendered
DOM. Header fields (name, location, follower counts) are still read from the DOM,
defensively: each tries several strategies and degrades to ``None`` instead of
raising. Use ``debug_dump`` to capture HTML when something stops resolving.
"""

from __future__ import annotations

import dataclasses
import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Page

from .session import BASE_URL

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(value: str | None) -> str | None:
    """Strip embedded HTML tags (e.g. Strava's <abbr> unit markup) and collapse
    whitespace."""
    if not value:
        return None
    text = re.sub(r"\s+", " ", _TAG_RE.sub("", value)).strip()
    return text or None


@dataclass
class WorkoutPost:
    activity_id: str
    url: str
    name: str | None = None
    sport_type: str | None = None
    description: str | None = None
    stats: dict[str, str] = field(default_factory=dict)
    start_date: str | None = None
    elapsed_time_s: int | None = None
    display_date: str | None = None
    location: str | None = None
    kudos_count: int | None = None
    comment_count: int | None = None
    photo_count: int = 0
    device_name: str | None = None


@dataclass
class AthleteProfile:
    athlete_id: str
    profile_url: str
    name: str | None = None
    location: str | None = None
    followers: int | None = None
    following: int | None = None
    workouts: list[WorkoutPost] = field(default_factory=list)
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _first_text(page: Page, selectors: list[str]) -> str | None:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            text = (locator.inner_text(timeout=2_000) or "").strip()
            if text:
                return text
        except Exception:
            continue
    return None


def _parse_count(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"([\d,.]+)\s*([KkMm]?)", text)
    if not match:
        return None
    number, suffix = match.group(1), match.group(2).lower()
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return None
    multiplier = {"k": 1_000, "m": 1_000_000}.get(suffix, 1)
    return int(value * multiplier)


def _extract_followers_following(page: Page) -> tuple[int | None, int | None]:
    """Read the Social Stats block, where label and count are separate elements:
    ``<li><span class="label">Following</span><a ...>39</a></li>``."""
    try:
        stats = page.evaluate(
            """() => {
                const out = {};
                document.querySelectorAll('ul.inline-stats li').forEach(li => {
                    const label = (li.querySelector('.label')?.innerText || '')
                        .trim().toLowerCase();
                    const val = (li.querySelector('a')?.innerText
                        || li.innerText || '').trim();
                    if (label.includes('follower')) out.followers = val;
                    else if (label.includes('following')) out.following = val;
                });
                return out;
            }"""
        )
        return _parse_count(stats.get("followers")), _parse_count(stats.get("following"))
    except Exception:
        return None, None


def _stats_to_dict(stats: list) -> dict[str, str]:
    """Strava stats come as paired slots: stat_one / stat_one_subtitle, etc.
    Fold them into {subtitle: value}, e.g. {'Distance': '3.00 mi', 'Pace': ...}."""
    raw = {s.get("key"): s.get("value") for s in stats if isinstance(s, dict)}
    out: dict[str, str] = {}
    for slot in ("one", "two", "three", "four"):
        label = _clean(raw.get(f"stat_{slot}_subtitle"))
        value = _clean(raw.get(f"stat_{slot}"))
        if label and value:
            out[label] = value
    return out


def _extract_feed_props(html_content: str) -> dict | None:
    """Pull and decode the activity feed micro-frontend's data-react-props JSON."""
    match = re.search(
        r'react-feed-component.*?data-react-props="([^"]*)"', html_content, re.S
    )
    if not match:
        return None
    try:
        return json.loads(html.unescape(match.group(1)))
    except (json.JSONDecodeError, ValueError):
        return None


def workout_from_entry(entry: dict) -> WorkoutPost | None:
    """Build a WorkoutPost from a feed ``preFetchedEntries`` entry, or None if the
    entry is not an activity (challenge, club post, suggestion, etc.)."""
    if entry.get("entity") != "Activity":
        return None
    a = entry.get("activity", {}) or {}
    loc = a.get("timeAndLocation", {}) or {}
    kc = a.get("kudosAndComments", {}) or {}
    photos = (a.get("mapAndPhotos", {}) or {}).get("photoList") or []
    activity_id = str(a.get("id") or "")
    return WorkoutPost(
        activity_id=activity_id,
        url=f"{BASE_URL}/activities/{activity_id}" if activity_id else "",
        name=_clean(a.get("activityName")),
        sport_type=a.get("type"),
        description=_clean(a.get("description")),
        stats=_stats_to_dict(a.get("stats", []) or []),
        start_date=a.get("startDate"),
        elapsed_time_s=a.get("elapsedTime"),
        display_date=loc.get("displayDateAtTime"),
        location=loc.get("location"),
        kudos_count=kc.get("kudosCount"),
        comment_count=len(kc.get("comments") or []),
        photo_count=len(photos),
        device_name=a.get("deviceName"),
    )


def workout_from_grouped_activity(a: dict) -> WorkoutPost:
    """Grouped activities (entity ``GroupActivity``) nest their members under a flat
    legacy schema (``activity_id``, ``activity_class_name``, ``name``, ...) that
    differs from the top-level feed shape, though ``stats`` is identical."""
    activity_id = str(a.get("activity_id") or a.get("entity_id") or "")
    return WorkoutPost(
        activity_id=activity_id,
        url=f"{BASE_URL}/activities/{activity_id}" if activity_id else "",
        name=_clean(a.get("name")),
        sport_type=a.get("type") or a.get("activity_class_name"),
        description=_clean(a.get("description")),
        stats=_stats_to_dict(a.get("stats", []) or []),
        start_date=a.get("start_date"),
        elapsed_time_s=a.get("elapsed_time"),
        display_date=a.get("start_date_local") or a.get("start_date"),
        location=a.get("location"),
        kudos_count=a.get("kudos_count"),
        comment_count=a.get("num_comments") or len(a.get("comments") or []),
        photo_count=len(a.get("photos") or []),
        device_name=a.get("device_name"),
    )


def workouts_from_entry(
    entry: dict, owner_athlete_id: str | None = None
) -> list[WorkoutPost]:
    """Expand a feed entry into the profile owner's workout posts.

    A ``GroupActivity`` bundles the activities of *several* athletes who worked out
    together, so we keep only members matching ``owner_athlete_id`` to avoid counting
    other people's runs."""
    entity = entry.get("entity")
    if entity == "Activity":
        post = workout_from_entry(entry)
        return [post] if post else []
    if entity == "GroupActivity":
        members = (entry.get("rowData", {}) or {}).get("activities", []) or []
        posts = []
        for m in members:
            if m.get("entity") != "Activity":
                continue
            if owner_athlete_id is not None and str(
                m.get("athlete_id")
            ) != str(owner_athlete_id):
                continue
            posts.append(workout_from_grouped_activity(m))
        return posts
    return []


def _extract_workouts(
    html_content: str, limit: int, owner_athlete_id: str | None = None
) -> list[WorkoutPost]:
    props = _extract_feed_props(html_content)
    if not props:
        return []
    entries = props.get("appContext", {}).get("preFetchedEntries", []) or []
    posts: list[WorkoutPost] = []
    for entry in entries:
        for post in workouts_from_entry(entry, owner_athlete_id):
            posts.append(post)
            if len(posts) >= limit:
                return posts
    return posts


def scrape_athlete(
    page: Page,
    athlete_id: str,
    *,
    max_workouts: int = 20,
    debug_dump_dir: Path | str | None = None,
) -> AthleteProfile:
    """Navigate to an athlete profile and extract a structured record."""
    profile_url = f"{BASE_URL}/athletes/{athlete_id}"
    page.goto(profile_url, wait_until="domcontentloaded", timeout=30_000)
    # Profile stats and the feed micro-frontend hydrate after initial load.
    page.wait_for_timeout(1_500)

    html_content = page.content()
    if debug_dump_dir:
        _dump(page, athlete_id, debug_dump_dir, html_content)

    name = _first_text(
        page,
        ["h1.athlete-name", '[data-testid="athlete-name"]', "header h1", "h1"],
    )
    location = _first_text(
        page, [".location", '[data-testid="location"]', ".athlete-location"]
    )
    followers, following = _extract_followers_following(page)

    return AthleteProfile(
        athlete_id=str(athlete_id),
        profile_url=profile_url,
        name=name,
        location=location,
        followers=followers,
        following=following,
        workouts=_extract_workouts(html_content, max_workouts, str(athlete_id)),
    )


def _dump(
    page: Page, athlete_id: str, debug_dump_dir: Path | str, html_content: str
) -> None:
    debug_dump_dir = Path(debug_dump_dir)
    debug_dump_dir.mkdir(parents=True, exist_ok=True)
    try:
        (debug_dump_dir / f"athlete_{athlete_id}.html").write_text(
            html_content, encoding="utf-8"
        )
        page.screenshot(
            path=str(debug_dump_dir / f"athlete_{athlete_id}.png"), full_page=True
        )
    except Exception:
        pass
