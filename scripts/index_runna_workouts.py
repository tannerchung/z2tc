#!/usr/bin/env python3
"""Scan local Strava activity caches for Runna & quality workouts and map to CATALOG_WORKOUTS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.workout_harvester import harvest_activities


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="JSON files or directories containing Strava activity lists (defaults to data/)",
    )
    args = parser.parse_args()

    search_roots = [Path(p) for p in args.paths] if args.paths else [ROOT / "data"]
    activities: list[dict] = []

    for p in search_roots:
        if p.is_file() and p.suffix == ".json":
            files = [p]
        elif p.is_dir():
            files = sorted(p.rglob("*.json"))
        else:
            continue
        for f in files:
            try:
                raw = json.loads(f.read_text())
            except Exception:
                continue
            if isinstance(raw, list):
                activities.extend(x for x in raw if isinstance(x, dict) and ("distance" in x or "workout_type" in x))
            elif isinstance(raw, dict):
                if "activities" in raw and isinstance(raw["activities"], list):
                    activities.extend(x for x in raw["activities"] if isinstance(x, dict))
                elif "distance" in raw and "name" in raw:
                    activities.append(raw)

    report = harvest_activities(activities)
    print(f"Scanned {report.total_scanned} activities -> {len(report.quality_sessions)} quality sessions")
    for cat, count in sorted(report.by_category_counts.items()):
        print(f"  - {cat}: {count}")
    if report.unindexed_candidates:
        print(f"\nUnindexed quality candidates ({len(report.unindexed_candidates)}):")
        for u in report.unindexed_candidates[:15]:
            print(f"  * [{u.detected_source}] {u.title} ({u.category})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
