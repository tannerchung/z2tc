"""Pluggable official chip-time lookup for race results.

NYRR is the default feed for club athletes. Other major marathons (Melbourne, Chicago,
Boston, etc.) can register adapters that search by runner name + race name + date.

Merge uses this layer *after* Strava title detection and *before* intake self-report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lib.data_feeds.nyrr import list_chip_races_for_search, nyrr_distance_to_category
from lib.data_feeds.rtrt import list_chip_races_for_search as rtrt_chip_races


@dataclass(frozen=True)
class ChipRace:
    start_date: str  # ISO YYYY-MM-DD
    category: str    # Daniels distance key, e.g. "Half Marathon"
    duration_s: int
    race_name: str
    source: str      # e.g. "nyrr", "athlinks"


class ChipLookupFeed(Protocol):
    """One results provider (NYRR RMS, future Melbourne/Boston adapters)."""

    name: str

    def lookup_runner(self, search_name: str) -> list[ChipRace]:
        """Return chip times for ``search_name`` from this feed."""


class NyrrChipFeed:
    name = "nyrr"

    def lookup_runner(self, search_name: str) -> list[ChipRace]:
        _rid, rows = list_chip_races_for_search(search_name.strip())
        out: list[ChipRace] = []
        for r in rows:
            cat = r.category or nyrr_distance_to_category(getattr(r, "distance_name", None))
            if not cat:
                continue
            out.append(
                ChipRace(
                    start_date=r.start_date,
                    category=cat,
                    duration_s=r.duration_s,
                    race_name=r.event_name,
                    source=self.name,
                )
            )
        return out


class RtrtChipFeed:
    name = "rtrt"

    def lookup_runner(self, search_name: str) -> list[ChipRace]:
        out: list[ChipRace] = []
        for r in rtrt_chip_races(search_name.strip()):
            out.append(
                ChipRace(
                    start_date=r.start_date,
                    category=r.category,
                    duration_s=r.duration_s,
                    race_name=r.race_name,
                    source=self.name,
                )
            )
        return out


_EXTERNAL_FEEDS: list[ChipLookupFeed] = [RtrtChipFeed()]


def all_chip_feeds(*, include_nyrr: bool = True) -> list[ChipLookupFeed]:
    feeds: list[ChipLookupFeed] = []
    if include_nyrr:
        feeds.append(NyrrChipFeed())
    feeds.extend(_EXTERNAL_FEEDS)
    return feeds


def build_chip_index(
    search_name: str,
    *,
    include_nyrr: bool = True,
    feeds: list[ChipLookupFeed] | None = None,
) -> tuple[dict[tuple[str, str], ChipRace], list[str]]:
    """Map ``(date_iso, category)`` → :class:`ChipRace` across feeds.

    First feed wins on duplicate keys. Returns ``(index, log_lines)`` for merge provenance.
    """
    index: dict[tuple[str, str], ChipRace] = {}
    log: list[str] = []
    for feed in feeds or all_chip_feeds(include_nyrr=include_nyrr):
        try:
            races = feed.lookup_runner(search_name)
        except (LookupError, OSError, RuntimeError) as exc:
            log.append(f"{feed.name}: lookup failed ({exc})")
            continue
        n = 0
        for cr in races:
            key = (cr.start_date[:10], cr.category)
            if key in index:
                continue
            index[key] = cr
            n += 1
        if n:
            log.append(f"{feed.name}: {n} chip time(s) for {search_name!r}")
    return index, log
