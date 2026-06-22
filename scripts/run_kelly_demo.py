#!/usr/bin/env python3
"""Run Kelly-shaped survey data through build-plan → replan → monitor (temp SQLite).

Default survey matches the ``tests/test_plan._daniels_athlete()`` regression fixture.
Point ``--survey`` at a JSON file, or use ``--from-intake-sheet`` to read the club
``Intake_responses`` tab (merged onto ``--defaults`` for Strava numerics).

For **real** athletes, build survey JSON from ``marathon-report`` + optional NYRR chip
times (see ``scripts/merge_report_nyrr_survey.py`` and ``main.py nyrr-races``), then pass
that file as ``--survey``.

**Strava history (optional)**

- ``--training PATH`` — use an existing ``training`` command JSONL (e.g. you already ran
  ``python main.py training <id> …``).
- Or ``--strava-id ID`` (or env ``Z2TC_KELLY_STRAVA_ID``) + ``--fetch-training`` — runs
  ``main.py training`` over a date window derived from the survey's ``race_date`` and
  ``block_weeks`` (needs your saved Strava session: ``python main.py login``).

Do **not** commit real athlete IDs or exports; pass them on the CLI or via env.

``--publish`` runs ``ingest-style`` + ``publish-sheet`` (Google token required).

Usage::

    # Fixture only, empty training (many AdherenceFlag events)
    python scripts/run_kelly_demo.py

    # Club Intake_responses (Google Sheets) — needs Hermes token; merges with --defaults
    python scripts/run_kelly_demo.py --from-intake-sheet --match-name "Kelly" \\
        --fetch-training --defaults tests/fixtures/survey_kelly.json

    # Reuse a JSONL you already scraped
    python scripts/run_kelly_demo.py --training output/marathon/training_12345678.jsonl \\
        --strava-id 12345678 --survey path/from/intake.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SURVEY = PROJECT_ROOT / "tests" / "fixtures" / "survey_kelly.json"
DEFAULT_ATHLETE_ID = "kelly-demo"


def _training_window_from_survey(survey_path: Path) -> tuple[date, date]:
    data = json.loads(survey_path.read_text(encoding="utf-8"))
    race = date.fromisoformat(str(data["race_date"]))
    block = int(data.get("block_weeks", 18))
    # Cover the plan block plus a few weeks before (Strava-derived baselines).
    start = race - timedelta(weeks=block + 4)
    end = date.today()
    if end < start:
        end = start + timedelta(weeks=1)
    return start, end


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--survey",
        type=Path,
        default=DEFAULT_SURVEY,
        help="SurveyInputs JSON (fixture or exported intake row).",
    )
    parser.add_argument(
        "--athlete-id",
        default=DEFAULT_ATHLETE_ID,
        help="SQLite store key for this run (default: kelly-demo).",
    )
    parser.add_argument(
        "--strava-id",
        default=os.environ.get("Z2TC_KELLY_STRAVA_ID", ""),
        help="Strava athlete id (or set Z2TC_KELLY_STRAVA_ID). Stored on Athlete row.",
    )
    parser.add_argument(
        "--training",
        type=Path,
        default=None,
        help="Existing training JSONL for monitor (skips fetch).",
    )
    parser.add_argument(
        "--fetch-training",
        action="store_true",
        help="Run main.py training with --strava-id over a window from survey race_date.",
    )
    parser.add_argument(
        "--training-start",
        type=str,
        default=None,
        help="Override fetch start YYYY-MM-DD (default: derived from survey).",
    )
    parser.add_argument(
        "--training-end",
        type=str,
        default=None,
        help="Override fetch end YYYY-MM-DD (default: today).",
    )
    parser.add_argument(
        "--training-delay",
        type=float,
        default=1.0,
        help="Seconds between weekly Strava requests when fetching (default 1.0).",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also run ingest-style + publish-sheet (needs Google token).",
    )
    parser.add_argument(
        "--from-intake-sheet",
        action="store_true",
        help="Load row from club spreadsheet Intake_responses (needs Google token).",
    )
    parser.add_argument(
        "--match-name",
        default="",
        help="With --from-intake-sheet: substring match on full_name (e.g. Kelly).",
    )
    parser.add_argument(
        "--defaults",
        type=Path,
        default=None,
        help="With --from-intake-sheet: base SurveyInputs JSON (default: --survey path).",
    )
    parser.add_argument(
        "--intake-tab",
        default="Intake_responses",
        help="Form responses tab name.",
    )
    parser.add_argument(
        "--spreadsheet-id",
        default=None,
        help="Workbook id (default Z2TC_CLUB_SPREADSHEET_ID / club workbook).",
    )
    args = parser.parse_args()

    tmp_survey: Path | None = None
    survey = args.survey
    strava_id = (args.strava_id or "").strip()

    if args.from_intake_sheet:
        if not args.match_name.strip():
            print("--match-name is required with --from-intake-sheet", file=sys.stderr)
            return 1
        defs = args.defaults if args.defaults is not None else survey
        if not defs.exists():
            print(f"Missing defaults/survey file: {defs}", file=sys.stderr)
            return 1
        from render.style import default_club_spreadsheet_id
        from store.intake_sheet import pull_survey_for_athlete
        from store.models import SurveyInputs

        defaults_obj = SurveyInputs.model_validate_json(
            defs.read_text(encoding="utf-8")
        )
        ss = args.spreadsheet_id or default_club_spreadsheet_id()
        merged, sid, row = pull_survey_for_athlete(
            defaults=defaults_obj,
            spreadsheet_id=ss,
            tab=args.intake_tab,
            match_name=args.match_name.strip(),
            match_strava_id=strava_id or None,
        )
        print(
            f"[intake] merged sheet row {row} from {args.intake_tab!r} (strava_id={sid!r})",
            file=sys.stderr,
        )
        fd, tmp_name = tempfile.mkstemp(suffix="_intake_survey.json", prefix="kelly_")
        tmp_survey = Path(tmp_name)
        with open(fd, "w", encoding="utf-8") as fh:
            fh.write(merged.model_dump_json(indent=2))
        survey = tmp_survey
        if sid and not strava_id:
            strava_id = sid
    elif not survey.exists():
        print(f"Missing survey file: {survey}", file=sys.stderr)
        return 1

    py = sys.executable
    main_py = PROJECT_ROOT / "main.py"
    athlete_id = args.athlete_id

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as dbf:
        db_path = Path(dbf.name)
    train_path: Path | None = None
    delete_train = False

    def run(cmd: list[str], *, timeout: float = 120.0) -> None:
        print("+", " ".join(cmd))
        r = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if r.stdout:
            print(r.stdout.rstrip())
        if r.stderr:
            print(r.stderr.rstrip(), file=sys.stderr)
        if r.returncode != 0:
            raise SystemExit(r.returncode)

    try:
        if args.training is not None:
            train_path = args.training.resolve()
            if not train_path.is_file():
                print(f"Not a file: {train_path}", file=sys.stderr)
                return 1
        elif args.fetch_training:
            if not strava_id:
                print(
                    "Need --strava-id or Z2TC_KELLY_STRAVA_ID for --fetch-training.",
                    file=sys.stderr,
                )
                return 1
            t_start, t_end = _training_window_from_survey(survey)
            if args.training_start:
                t_start = date.fromisoformat(args.training_start)
            if args.training_end:
                t_end = date.fromisoformat(args.training_end)
            train_path = Path(
                tempfile.mkstemp(suffix=".jsonl", prefix="kelly_strava_")[1]
            )
            delete_train = True
            # Wide timeout: one HTTP-ish interaction per week.
            weeks = max(1, (t_end - t_start).days // 7 + 2)
            timeout_s = min(600.0, 60.0 + float(args.training_delay) * weeks * 2.0)
            run(
                [
                    py,
                    str(main_py),
                    "training",
                    strava_id,
                    "--start",
                    t_start.isoformat(),
                    "--end",
                    t_end.isoformat(),
                    "--out",
                    str(train_path),
                    "--delay",
                    str(args.training_delay),
                ],
                timeout=timeout_s,
            )
        else:
            train_path = Path(tempfile.mkstemp(suffix=".jsonl", prefix="kelly_train_")[1])
            delete_train = True
            train_path.write_text("", encoding="utf-8")

        assert train_path is not None

        build_cmd = [
            py,
            str(main_py),
            "build-plan",
            athlete_id,
            "--survey",
            str(survey.resolve()),
            "--db",
            str(db_path),
        ]
        if strava_id:
            build_cmd.extend(["--strava-id", strava_id])
        run(build_cmd)

        run([py, str(main_py), "replan", athlete_id, "--db", str(db_path)])
        run(
            [
                py,
                str(main_py),
                "monitor",
                athlete_id,
                "--training",
                str(train_path),
                "--db",
                str(db_path),
            ]
        )
        if args.publish:
            style_out = Path(tempfile.mkstemp(suffix="_style.json", prefix="kelly_")[1])
            try:
                run(
                    [
                        py,
                        str(main_py),
                        "ingest-style",
                        "--out",
                        str(style_out),
                    ],
                    timeout=180.0,
                )
                run(
                    [
                        py,
                        str(main_py),
                        "publish-sheet",
                        athlete_id,
                        "--style-bundle",
                        str(style_out),
                        "--db",
                        str(db_path),
                    ],
                    timeout=120.0,
                )
            finally:
                style_out.unlink(missing_ok=True)
        print("\nKelly demo finished OK.")
    finally:
        if tmp_survey is not None:
            tmp_survey.unlink(missing_ok=True)
        print(f"\nTemp DB (delete when done): {db_path}")
        if train_path is not None:
            print(f"Training JSONL: {train_path}")
            if delete_train:
                print("(temp file — delete if you do not need it)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
