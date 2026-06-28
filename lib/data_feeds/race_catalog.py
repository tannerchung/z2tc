"""Known race → results-API mappings for chip-time lookup.

Grows incrementally as we document each event's provider and slug. Merge chip feeds
consult this catalog before hitting provider APIs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RaceCatalogEntry:
    provider: str       # e.g. "rtrt", "nyrr"
    event_slug: str     # provider event id (RTRT: MM-NIKEMM-2025)
    race_date: str      # ISO YYYY-MM-DD
    race_name: str
    course: str = "marathon"  # RTRT course key → Daniels category via rtrt.COURSE_TO_CATEGORY


# Incremental catalog — add entries as APIs are verified.
RACE_CATALOG: tuple[RaceCatalogEntry, ...] = (
    RaceCatalogEntry(
        provider="rtrt",
        event_slug="MM-NIKEMM-2025",
        race_date="2025-10-11",
        race_name="Nike Melbourne Marathon",
        course="marathon",
    ),
)


def catalog_for_provider(provider: str) -> list[RaceCatalogEntry]:
    return [e for e in RACE_CATALOG if e.provider == provider]
