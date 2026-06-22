"""Unit tests for ``lib.marathon_calendar``."""

from __future__ import annotations

from lib.marathon_calendar import (
    canonical_marathon_key,
    resolve_race_date,
    year_hint_from_iso,
)


def test_resolves_majors_with_sponsor_prefixes() -> None:
    assert resolve_race_date("Bank of America Chicago Marathon", 2026) == "2026-10-11"
    assert resolve_race_date("TCS New York City Marathon", 2026) == "2026-11-01"
    assert resolve_race_date("BMW Berlin Marathon", 2026) == "2026-09-27"
    assert resolve_race_date("Boston", 2026) == "2026-04-20"


def test_canonical_key_aliases() -> None:
    assert canonical_marathon_key("NYC Marathon") == "new_york_city"
    assert canonical_marathon_key("new york") == "new_york_city"
    assert canonical_marathon_key("Chicago Marathon") == "chicago"


def test_unknown_or_missing_year() -> None:
    assert resolve_race_date("Some Local Trail Marathon", 2026) is None
    assert resolve_race_date("Chicago Marathon", 2099) is None
    assert resolve_race_date("", 2026) is None


def test_single_known_year_resolves_without_year_arg() -> None:
    # Chicago currently has exactly one known year, so it resolves without a hint.
    assert resolve_race_date("Chicago Marathon") == "2026-10-11"


def test_year_hint_from_iso() -> None:
    assert year_hint_from_iso(None, "2026-10-09", "2026-10-12") == 2026
    assert year_hint_from_iso("", None) is None
