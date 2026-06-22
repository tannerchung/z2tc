#!/usr/bin/env python3
"""One-off bulk import: club roster → SQLite store.

For each athlete: ensure a Strava marathon-report exists (scrape if missing), pull their
Intake row, merge Strava-derived metrics (`vdot`/`w_now`/`p_history`/longest + break/cross-
training), and `build-plan` the baseline into the SQLite store.

This is a **transitional** tool. The intended future is intake + Strava landing in SQLite
directly at capture time; this script just backfills the athletes we already have data for.

Usage::

    python scripts/import_all_athletes.py                 # all roster athletes
    python scripts/import_all_athletes.py --only cindy-kim # one athlete
    python scripts/import_all_athletes.py --dry-run        # print the steps only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
SCRAPE_TIMEOUT_S = 900   # week-by-week Strava scan can be slow
STEP_TIMEOUT_S = 180


@dataclass(frozen=True)
class Roster:
    athlete_id: str   # store slug
    name: str         # Intake full_name / NYRR search
    strava_id: str


# Known club roster (name → Strava id). Reports for all but Cindy already live in output/.
ROSTER = [
    Roster("kelly-hession", "Kelly Hession", "42251408"),
    Roster("nina-sayson", "Nina Sayson", "61628075"),
    Roster("rohan-shetty", "Rohan Shetty", "107176083"),
    Roster("michelle-kroll", "Michelle Kroll", "135690507"),
    Roster("emily-bennett", "Emily Bennett", "165030659"),
    Roster("tamara-oprea", "Tamara Oprea", "15353069"),
    Roster("gaurav-goel", "Gaurav Goel", "135242872"),
    Roster("cindy-kim", "Cindy Kim", "128394498"),
]

# A valid SurveyInputs base; the sheet overlays intake fields and the merge overlays the
# Strava-derived numbers, so these placeholders are all overwritten downstream.
BASE_DEFAULTS = {
    "name": "(intake)",
    "vdot": 40.0,
    "goal_marathon_s": 14400,
    "w_now": 20.0,
    "p_history": 30.0,
    "longest_run_mi": 12.0,
    "days_per_week": 5,
    "race_date": "2026-10-11",
    "block_weeks": 18,
    "race_name": "Marathon",
    "secondary_races": [],
}

REPORT_DIRS = [
    PROJECT_ROOT / "output" / "marathon",
    PROJECT_ROOT / "output" / "kelly_strava",
]
SCRAPE_OUT_DIR = PROJECT_ROOT / "output" / "marathon"


def _find(kind: str, strava_id: str) -> Path | None:
    """Locate report_<id>.json / training_<id>.jsonl across known output dirs."""
    suffix = "json" if kind == "report" else "jsonl"
    for d in REPORT_DIRS:
        p = d / f"{kind}_{strava_id}.{suffix}"
        if p.exists():
            return p
    return None


def _run(cmd: list[str], *, timeout: int, dry: bool) -> bool:
    print("  $", " ".join(cmd))
    if dry:
        return True
    try:
        r = subprocess.run(cmd, cwd=PROJECT_ROOT, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"  ! timed out after {timeout}s", file=sys.stderr)
        return False
    return r.returncode == 0


def import_one(a: Roster, base_path: Path, tmp: Path, *, dry: bool) -> str:
    print(f"\n=== {a.name} ({a.athlete_id}, strava {a.strava_id}) ===")

    report = _find("report", a.strava_id)
    training = _find("training", a.strava_id)
    if report is None or training is None:
        print("  no Strava report on disk → scraping marathon-report")
        if not _run([PY, "main.py", "marathon-report", a.strava_id], timeout=SCRAPE_TIMEOUT_S, dry=dry):
            return "scrape_failed"
        report, training = _find("report", a.strava_id), _find("training", a.strava_id)
        if not dry and (report is None or training is None):
            return "scrape_no_output"
    report = report or (SCRAPE_OUT_DIR / f"report_{a.strava_id}.json")
    training = training or (SCRAPE_OUT_DIR / f"training_{a.strava_id}.jsonl")

    intake_json = tmp / f"{a.strava_id}_intake.json"
    if not _run(
        [PY, "main.py", "pull-intake", "--match-strava-id", a.strava_id,
         "--defaults", str(base_path), "--out", str(intake_json)],
        timeout=STEP_TIMEOUT_S, dry=dry,
    ):
        return "pull_intake_failed"

    survey_json = tmp / f"{a.strava_id}_survey.json"
    if not _run(
        [PY, "scripts/merge_report_nyrr_survey.py", "--base", str(intake_json),
         "--report", str(report), "--training", str(training), "-o", str(survey_json)],
        timeout=STEP_TIMEOUT_S, dry=dry,
    ):
        return "merge_failed"

    if not _run(
        [PY, "main.py", "build-plan", a.athlete_id,
         "--survey", str(survey_json), "--strava-id", a.strava_id],
        timeout=STEP_TIMEOUT_S, dry=dry,
    ):
        return "build_plan_failed"
    return "ok"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=None, help="Import a single athlete by slug (e.g. cindy-kim).")
    ap.add_argument("--dry-run", action="store_true", help="Print steps without running them.")
    args = ap.parse_args()

    roster = [a for a in ROSTER if (args.only is None or a.athlete_id == args.only)]
    if not roster:
        print(f"No roster match for --only {args.only!r}", file=sys.stderr)
        return 1

    results: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="z2tc_import_") as td:
        tmp = Path(td)
        base_path = tmp / "base_defaults.json"
        base_path.write_text(json.dumps(BASE_DEFAULTS), encoding="utf-8")
        for a in roster:
            try:
                results[a.athlete_id] = import_one(a, base_path, tmp, dry=args.dry_run)
            except Exception as exc:  # keep going; report at the end
                results[a.athlete_id] = f"error: {exc}"

    print("\n=== import summary ===")
    for slug, status in results.items():
        print(f"  {slug:16} {status}")
    failures = [s for s in results.values() if s != "ok"]
    return 1 if failures and not args.dry_run else 0


if __name__ == "__main__":
    raise SystemExit(main())
