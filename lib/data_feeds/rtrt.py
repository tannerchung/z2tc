"""Read-only client for RTRT.me live results (chip times).

The web tracker at ``track.rtrt.me`` POSTs form-encoded JSON to ``api.rtrt.me``. Profile
lookup by full name works on ``/events/{slug}/profiles``; finish time is on
``/events/{slug}/profiles/{pid}/splits`` (``M-FINISH`` ``netTime``).
"""

from __future__ import annotations

import json
import random
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from lib.data_feeds.race_catalog import RaceCatalogEntry, catalog_for_provider

API_ROOT = "https://api.rtrt.me"
APP_ID = "52139b797871851e0800638e"
DEFAULT_TIMEOUT_S = 30.0

COURSE_TO_CATEGORY: dict[str, str] = {
    "marathon": "Marathon",
    "half": "Half Marathon",
    "half marathon": "Half Marathon",
    "10k": "10K",
    "5k": "5K",
}


def _new_token() -> str:
    return random.randbytes(10).hex().upper()


def _post_form(path: str, fields: dict[str, Any], *, timeout: float = DEFAULT_TIMEOUT_S) -> Any:
    data = urllib.parse.urlencode({k: v for k, v in fields.items() if v is not None}).encode()
    req = urllib.request.Request(
        f"{API_ROOT}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"RTRT HTTP {exc.code}: {body[:200]}") from exc


def _base_fields(event_slug: str, token: str) -> dict[str, Any]:
    return {
        "event": event_slug,
        "sess": 0,
        "appid": APP_ID,
        "token": token,
        "source": "webtracker",
    }


def search_profiles(event_slug: str, name: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> list[dict]:
    """Return profile rows whose ``name`` matches ``name`` (case-insensitive)."""
    token = _new_token()
    payload = _post_form(
        f"/events/{event_slug}/profiles",
        {**_base_fields(event_slug, token), "name": name.strip(), "max": 20},
        timeout=timeout,
    )
    if payload.get("error"):
        return []
    want = name.strip().casefold()
    return [p for p in payload.get("list", []) if str(p.get("name", "")).casefold() == want]


def fetch_profile(event_slug: str, pid: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> dict | None:
    token = _new_token()
    payload = _post_form(
        f"/events/{event_slug}/profiles/{pid}",
        _base_fields(event_slug, token),
        timeout=timeout,
    )
    rows = payload.get("list") or []
    return rows[0] if rows else None


def fetch_finish_seconds(event_slug: str, pid: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> int | None:
    token = _new_token()
    payload = _post_form(
        f"/events/{event_slug}/profiles/{pid}/splits",
        _base_fields(event_slug, token),
        timeout=timeout,
    )
    for split in payload.get("list") or []:
        point = str(split.get("point") or split.get("alias") or "")
        if point.endswith("FINISH") or split.get("isFinish"):
            net = split.get("netTime") or split.get("time")
            if isinstance(net, str):
                return _parse_hms(net)
    return None


def _parse_hms(text: str) -> int | None:
    m = re.match(r"^(\d+):(\d{2}):(\d{2})(?:\.(\d+))?$", text.strip())
    if not m:
        return None
    h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return h * 3600 + mi * 60 + s


@dataclass(frozen=True)
class RtrtChipResult:
    start_date: str
    category: str
    duration_s: int
    race_name: str
    pid: str
    bib: str | None


def lookup_runner_at_event(
    entry: RaceCatalogEntry,
    search_name: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> RtrtChipResult | None:
    profiles = search_profiles(entry.event_slug, search_name, timeout=timeout)
    if not profiles:
        return None
    profile = profiles[0]
    pid = str(profile.get("pid") or "")
    if not pid:
        return None
    duration_s = fetch_finish_seconds(entry.event_slug, pid, timeout=timeout)
    if duration_s is None:
        return None
    course = str(profile.get("course") or entry.course)
    category = COURSE_TO_CATEGORY.get(course.casefold(), COURSE_TO_CATEGORY.get(entry.course, "Marathon"))
    return RtrtChipResult(
        start_date=entry.race_date,
        category=category,
        duration_s=duration_s,
        race_name=entry.race_name,
        pid=pid,
        bib=str(profile.get("bib")) if profile.get("bib") else None,
    )


def list_chip_races_for_search(
    search_name: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> list[RtrtChipResult]:
    """Chip times for ``search_name`` across cataloged RTRT events."""
    out: list[RtrtChipResult] = []
    for entry in catalog_for_provider("rtrt"):
        try:
            hit = lookup_runner_at_event(entry, search_name, timeout=timeout)
        except (OSError, RuntimeError, ValueError):
            continue
        if hit is not None:
            out.append(hit)
    return out
