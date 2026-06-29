#!/usr/bin/env python3
"""One-off, idempotent migration: upgrade a pre-season-scoping store to the season-scoped schema.

Early stores keyed ``survey_baselines`` / ``events`` / ``plan_artifacts`` by ``athlete_id`` only.
The current schema (``store/db.py``) scopes them by ``season_id`` (one season per marathon block).
This migration adds the missing ``season_id`` columns, creates one **active** season per athlete
(labelled from the survey baseline's race), backfills ``season_id`` on the existing rows, and rekeys
``survey_baselines`` to ``season_id``. All existing events (coach overrides, adherence, etc.) and
baselines are preserved and attached to the new season.

Idempotent: if the DB is already season-scoped (events has ``season_id``), it does nothing.

    python scripts/migrate_db_to_seasons.py            # default output/z2tc.db (backs up first)
    python scripts/migrate_db_to_seasons.py --db PATH
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from store.db import default_db_path  # noqa: E402


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def migrate(db_path: Path) -> int:
    if not db_path.exists():
        print(f"No DB at {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if "season_id" in _columns(conn, "events"):
        print("Already season-scoped (events.season_id present) — nothing to do.")
        return 0

    backup = db_path.with_suffix(db_path.suffix + f".bak-{datetime.now():%Y%m%d%H%M%S}")
    shutil.copy2(db_path, backup)
    print(f"Backed up {db_path} -> {backup}")

    # 1) One active season per athlete, labelled from the survey baseline's race.
    survey_by_athlete = {
        r["athlete_id"]: json.loads(r["payload_json"])
        for r in conn.execute("SELECT athlete_id, payload_json FROM survey_baselines")
    }
    season_by_athlete: dict[str, str] = {}
    for r in conn.execute("SELECT id FROM athletes"):
        aid = r["id"]
        survey = survey_by_athlete.get(aid, {})
        race_name = (survey.get("race_name") or "").strip()
        race_date = survey.get("race_date")
        label = f"{race_name} {race_date}".strip() or "Season 1"
        sid = str(uuid.uuid4())
        season_by_athlete[aid] = sid
        conn.execute(
            """INSERT INTO seasons (id, athlete_id, label, race_date, status, created_at, meta_json)
               VALUES (?, ?, ?, ?, 'active', ?, '{}')""",
            (sid, aid, label, race_date, _now()),
        )
        print(f"  season {sid}  {aid}  [{label}]")

    def _season_for(aid: str) -> str:
        return season_by_athlete.get(aid) or conn.execute(
            "SELECT id FROM seasons WHERE athlete_id=? LIMIT 1", (aid,)
        ).fetchone()["id"]

    # 2) events: add season_id, backfill from the athlete's season.
    conn.execute("ALTER TABLE events ADD COLUMN season_id TEXT")
    for r in conn.execute("SELECT DISTINCT athlete_id FROM events"):
        conn.execute(
            "UPDATE events SET season_id=? WHERE athlete_id=?",
            (_season_for(r["athlete_id"]), r["athlete_id"]),
        )

    # 3) plan_artifacts: add season_id + resolved_inputs_json, backfill season_id.
    art_cols = _columns(conn, "plan_artifacts")
    if "season_id" not in art_cols:
        conn.execute("ALTER TABLE plan_artifacts ADD COLUMN season_id TEXT")
    if "resolved_inputs_json" not in art_cols:
        conn.execute("ALTER TABLE plan_artifacts ADD COLUMN resolved_inputs_json TEXT")
    for r in conn.execute("SELECT DISTINCT athlete_id FROM plan_artifacts"):
        conn.execute(
            "UPDATE plan_artifacts SET season_id=? WHERE athlete_id=?",
            (_season_for(r["athlete_id"]), r["athlete_id"]),
        )

    # 4) survey_baselines: rekey from athlete_id to season_id (PRIMARY KEY change → rebuild table).
    conn.execute(
        """CREATE TABLE survey_baselines_new (
               season_id TEXT PRIMARY KEY,
               athlete_id TEXT NOT NULL,
               updated_at TEXT NOT NULL,
               payload_json TEXT NOT NULL
           )"""
    )
    for r in conn.execute("SELECT athlete_id, updated_at, payload_json FROM survey_baselines"):
        conn.execute(
            "INSERT INTO survey_baselines_new (season_id, athlete_id, updated_at, payload_json) VALUES (?, ?, ?, ?)",
            (_season_for(r["athlete_id"]), r["athlete_id"], r["updated_at"], r["payload_json"]),
        )
    conn.execute("DROP TABLE survey_baselines")
    conn.execute("ALTER TABLE survey_baselines_new RENAME TO survey_baselines")

    conn.commit()
    conn.close()
    print("Migration complete. Open the store to create the season indexes (init_schema).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=None, help=f"SQLite path (default: {default_db_path()}).")
    args = ap.parse_args()
    return migrate(Path(args.db) if args.db else default_db_path())


if __name__ == "__main__":
    raise SystemExit(main())
