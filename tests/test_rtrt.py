"""Tests for RTRT chip-time client (live API when network available)."""

from __future__ import annotations

import pytest

from lib.data_feeds.rtrt import fetch_finish_seconds, list_chip_races_for_search, search_profiles


def test_rtrt_melbourne_cindy_kim():
  results = list_chip_races_for_search("Cindy Kim")
  assert results, "expected Melbourne catalog hit for Cindy Kim"
  mel = next(r for r in results if r.start_date == "2025-10-11")
  assert mel.category == "Marathon"
  assert mel.duration_s == pytest.approx(4 * 3600 + 24, abs=2)


def test_rtrt_search_profiles_exact_name():
  profiles = search_profiles("MM-NIKEMM-2025", "Cindy Kim")
  assert profiles and profiles[0]["pid"] == "R4AVLTJM"
  secs = fetch_finish_seconds("MM-NIKEMM-2025", "R4AVLTJM")
  assert secs == pytest.approx(4 * 3600 + 24, abs=2)
