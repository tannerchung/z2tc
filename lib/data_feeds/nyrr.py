"""Read-only client for NYRR official results (chip times) via the public RMS API.

The Angular app at https://results.nyrr.org/ loads ``settings.rmsApi`` from
``/GetSettings/rms-settings.rjs``; race rows are fetched with POST JSON to that base.

This module does not scrape Strava; it only queries NYRR for times coaches use to
override GPS/watch splits when building ``SurveyInputs`` / VDOT inputs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SETTINGS_URL = "https://results.nyrr.org/GetSettings/rms-settings.rjs"
DEFAULT_TIMEOUT_S = 60.0
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _http_json_post(url: str, payload: dict[str, Any], *, timeout: float) -> Any:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _BROWSER_UA,
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def fetch_rms_api_base(*, timeout: float = DEFAULT_TIMEOUT_S) -> str:
    """Return the RMS API root (e.g. ``https://rmsprodapi.nyrr.org/api/v2``)."""
    try:
        req = Request(SETTINGS_URL, headers={"User-Agent": _BROWSER_UA})
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
    except (OSError, HTTPError, URLError) as exc:
        raise RuntimeError(f"NYRR settings fetch failed: {exc}") from exc
    m = re.search(r"var\s+settings\s*=\s*(\{.*\})\s*;?\s*$", text.strip(), re.DOTALL)
    if not m:
        m = re.search(r"var\s+settings\s*=\s*(\{.*\})", text, re.DOTALL)
    if not m:
        raise RuntimeError("Could not parse NYRR settings script")
    data = json.loads(m.group(1))
    base = data.get("rmsApi")
    if not base or not isinstance(base, str):
        raise RuntimeError("rmsApi missing from NYRR settings")
    return base.rstrip("/")


def search_runners(
    search_string: str,
    *,
    page_index: int = 1,
    page_size: int = 10,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """POST ``/runners/search``; returns ``{totalItems, items:[...]}``."""
    base = fetch_rms_api_base(timeout=timeout)
    return _http_json_post(
        f"{base}/runners/search",
        {
            "searchString": search_string.strip(),
            "pageIndex": page_index,
            "pageSize": page_size,
            "sortColumn": None,
            "sortDescending": False,
        },
        timeout=timeout,
    )


def runner_races(
    runner_id: int,
    *,
    page_index: int = 1,
    page_size: int = 50,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """POST ``/runners/races`` for one RMS runner id (from search results)."""
    base = fetch_rms_api_base(timeout=timeout)
    return _http_json_post(
        f"{base}/runners/races",
        {"runnerId": runner_id, "pageIndex": page_index, "pageSize": page_size},
        timeout=timeout,
    )


def parse_nyrr_clock(actual_time: str) -> int | None:
    """Parse RMS ``actualTime`` like ``1:45:30`` or ``0:53:16`` to seconds."""
    s = str(actual_time or "").strip()
    if not s:
        return None
    parts = s.split(":")
    try:
        if len(parts) == 3:
            h, mi, sec = parts
            return int(h) * 3600 + int(mi) * 60 + int(float(sec))
        if len(parts) == 2:
            mi, sec = parts
            return int(mi) * 60 + int(float(sec))
    except (TypeError, ValueError):
        return None
    return None


def nyrr_distance_to_category(distance_name: str | None) -> str | None:
    """Map RMS ``distanceName`` to ``engine.analyze`` / VDOT race categories."""
    d = str(distance_name or "").strip().lower()
    if "half-marathon" in d or d == "half-marathon":
        return "Half Marathon"
    if "marathon" in d and "half" not in d:
        return "Marathon"
    if "10 kilometer" in d:
        return "10K"
    if "5 kilometer" in d:
        return "5K"
    return None


@dataclass(frozen=True)
class NyrrRaceRow:
    """One row from ``/runners/races`` (chip time)."""

    event_name: str
    start_date: str  # YYYY-MM-DD
    category: str | None
    duration_s: int
    bib: str | None


def list_chip_races_for_search(
    search_string: str,
    *,
    exclude_virtual: bool = True,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> tuple[int, list[NyrrRaceRow]]:
    """Search by name, return ``(runner_id_used, chip_races_newest_first)``."""
    data = search_runners(search_string, page_size=15, timeout=timeout)
    items = data.get("items") or []
    if not items:
        raise LookupError(f"No NYRR runners matched {search_string!r}")
    rid = int(items[0]["runnerId"])
    races_resp = runner_races(rid, page_size=100, timeout=timeout)
    out: list[NyrrRaceRow] = []
    for it in races_resp.get("items") or []:
        name = str(it.get("eventName") or "")
        if exclude_virtual and "virtual" in name.lower():
            continue
        cat = nyrr_distance_to_category(it.get("distanceName"))
        if not cat:
            continue
        ds = it.get("startDateTime") or ""
        start_date = ds[:10] if len(ds) >= 10 else ""
        secs = parse_nyrr_clock(str(it.get("actualTime") or ""))
        if not start_date or secs is None:
            continue
        out.append(
            NyrrRaceRow(
                event_name=name,
                start_date=start_date,
                category=cat,
                duration_s=secs,
                bib=str(it.get("bib") or "") or None,
            )
        )
    return rid, out
