"""Official published marathon dates → ISO ``race_date``.

The club intake form captures the marathon *name* ("Chicago Marathon") but not its
date, and athletes mistype dates. Race dates are officially published, so we resolve
``race_name`` → ``YYYY-MM-DD`` here instead of trusting free text.

Extend ``MARATHON_DATES`` per year as fields are confirmed. ``resolve_race_date``
normalizes sponsor prefixes/suffixes (e.g. "Bank of America Chicago Marathon",
"TCS New York City Marathon") via ``_ALIASES`` before lookup.
"""

from __future__ import annotations

import re

# canonical key -> {year: ISO date}. Dates are officially published; cite when adding.
MARATHON_DATES: dict[str, dict[int, str]] = {
    # Abbott World Marathon Majors (2026 calendar confirmed).
    "tokyo": {2026: "2026-03-01"},
    "boston": {2026: "2026-04-20"},
    "london": {2026: "2026-04-26"},
    "sydney": {2026: "2026-08-30"},
    "berlin": {2026: "2026-09-27"},
    "chicago": {2026: "2026-10-11"},
    "new_york_city": {2026: "2026-11-01"},
    # Major-candidate / popular series with confirmed 2026 dates.
    "cape_town": {2026: "2026-05-24"},
    "shanghai": {2026: "2026-12-06"},
}

# normalized-name needle -> canonical key. Longer/more-specific needles first.
_ALIASES: list[tuple[str, str]] = [
    ("new york city", "new_york_city"),
    ("new york", "new_york_city"),
    ("nyc", "new_york_city"),
    ("cape town", "cape_town"),
    ("chicago", "chicago"),
    ("boston", "boston"),
    ("london", "london"),
    ("berlin", "berlin"),
    ("tokyo", "tokyo"),
    ("sydney", "sydney"),
    ("shanghai", "shanghai"),
]


def _normalize(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())


def canonical_marathon_key(name: str | None) -> str | None:
    """Map a free-text marathon name to a canonical key, tolerating sponsor prefixes."""
    h = _normalize(name or "")
    if not h:
        return None
    for needle, key in _ALIASES:
        if needle in h:
            return key
    return None


def resolve_race_date(name: str | None, year: int | None = None) -> str | None:
    """Return the official ISO date for ``name`` in ``year`` (or any year if ``year`` is
    ``None`` and only one is known). ``None`` when the marathon/year is not in the table."""
    key = canonical_marathon_key(name)
    if not key:
        return None
    by_year = MARATHON_DATES.get(key)
    if not by_year:
        return None
    if year is not None:
        return by_year.get(year)
    if len(by_year) == 1:
        return next(iter(by_year.values()))
    return None


def year_hint_from_iso(*iso_dates: str | None) -> int | None:
    """First 4-digit year found in any ISO date string (e.g. an arrival date), else None."""
    for s in iso_dates:
        m = re.match(r"(\d{4})-\d{2}-\d{2}", str(s or ""))
        if m:
            return int(m.group(1))
    return None
