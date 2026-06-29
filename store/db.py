"""Thin SQLite persistence (no ORM). DB file under ``output/z2tc.db`` by default.

The store is **season-scoped**: an athlete (the person) has one or more seasons (marathon
blocks), and a survey baseline, event log, and plan artifacts all hang off a *season*. The
public methods still take ``athlete_id`` and resolve the athlete's **active** season when
``season_id`` is omitted, so single-season callers need no changes; a default season is
created on first write if none exists.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from engine.plan.models import AthleteInputs, TrainingPlan

from .models import (
    Athlete,
    DossierSnapshot,
    PlanArtifact,
    Publication,
    Season,
    SurveyInputs,
    TrainingBlock,
)
from .serialization import (
    athlete_inputs_fingerprint,
    athlete_inputs_to_dict,
    training_plan_from_dict,
    training_plan_to_dict,
)


# Bump when the schema below changes. Stored in SQLite's `PRAGMA user_version` so a later migration
# step (and analysis tooling) can tell which schema a DB file was last initialized at. New tables use
# `CREATE TABLE IF NOT EXISTS`; column additions to existing tables are handled by `_migrate` below.
SCHEMA_VERSION = 7

# Config key for the cached club-workbook style bundle (StyleSpec + spreadsheet id), folded into the
# store so a publish no longer depends on the output/club_workbook_style.json file surviving.
STYLE_BUNDLE_KEY = "club_workbook_style"


def default_db_path(project_root: Path | None = None) -> Path:
    root = project_root or Path(__file__).resolve().parents[1]
    out = root / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out / "z2tc.db"


class Store:
    def __init__(self, db_path: Path | None = None, *, project_root: Path | None = None) -> None:
        self.path = db_path or default_db_path(project_root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), timeout=30)
        self._conn.row_factory = sqlite3.Row
        self.init_schema()

    def close(self) -> None:
        self._conn.close()

    def init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS athletes (
                id TEXT PRIMARY KEY,
                strava_athlete_id TEXT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                meta_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS seasons (
                id TEXT PRIMARY KEY,
                athlete_id TEXT NOT NULL REFERENCES athletes(id),
                label TEXT NOT NULL,
                race_date TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                meta_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (athlete_id) REFERENCES athletes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_seasons_athlete ON seasons(athlete_id, status);
            CREATE TABLE IF NOT EXISTS survey_baselines (
                season_id TEXT PRIMARY KEY REFERENCES seasons(id),
                athlete_id TEXT NOT NULL REFERENCES athletes(id),
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                FOREIGN KEY (season_id) REFERENCES seasons(id),
                FOREIGN KEY (athlete_id) REFERENCES athletes(id)
            );
            CREATE TABLE IF NOT EXISTS plan_artifacts (
                id TEXT PRIMARY KEY,
                season_id TEXT REFERENCES seasons(id),
                athlete_id TEXT NOT NULL REFERENCES athletes(id),
                created_at TEXT NOT NULL,
                inputs_hash TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                resolved_inputs_json TEXT,
                engine_version TEXT,
                club_policy_version TEXT,
                FOREIGN KEY (season_id) REFERENCES seasons(id),
                FOREIGN KEY (athlete_id) REFERENCES athletes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_artifacts_season ON plan_artifacts(season_id, created_at);
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                season_id TEXT REFERENCES seasons(id),
                athlete_id TEXT NOT NULL REFERENCES athletes(id),
                ts TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                FOREIGN KEY (season_id) REFERENCES seasons(id),
                FOREIGN KEY (athlete_id) REFERENCES athletes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_events_athlete ON events(athlete_id, ts);
            CREATE INDEX IF NOT EXISTS idx_events_season ON events(season_id, ts);
            CREATE TABLE IF NOT EXISTS training_blocks (
                id TEXT PRIMARY KEY,
                athlete_id TEXT NOT NULL,
                strava_athlete_id TEXT,
                source TEXT NOT NULL DEFAULT 'strava',
                scraped_at TEXT NOT NULL,
                marathon_date TEXT,
                marathon_name TEXT,
                marathon_time_s INTEGER,
                block_start TEXT,
                block_end TEXT,
                weeks_json TEXT NOT NULL,
                report_json TEXT,
                profile_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_blocks_athlete ON training_blocks(athlete_id, marathon_date);
            CREATE INDEX IF NOT EXISTS idx_blocks_strava ON training_blocks(strava_athlete_id, marathon_date);
            CREATE TABLE IF NOT EXISTS narrative_renders (
                id TEXT PRIMARY KEY,
                season_id TEXT REFERENCES seasons(id),
                athlete_id TEXT NOT NULL REFERENCES athletes(id),
                created_at TEXT NOT NULL,
                surface TEXT NOT NULL,
                template_version TEXT NOT NULL,
                prompt_version TEXT,
                llm_model TEXT,
                source TEXT NOT NULL,
                deterministic_text TEXT NOT NULL,
                final_text TEXT NOT NULL,
                changed INTEGER NOT NULL DEFAULT 0,
                char_delta INTEGER NOT NULL DEFAULT 0,
                guard_passed INTEGER NOT NULL DEFAULT 1,
                signals_json TEXT NOT NULL DEFAULT '{}',
                inputs_fingerprint TEXT NOT NULL DEFAULT '',
                plan_artifact_id TEXT REFERENCES plan_artifacts(id),
                FOREIGN KEY (season_id) REFERENCES seasons(id),
                FOREIGN KEY (athlete_id) REFERENCES athletes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_narr_athlete ON narrative_renders(athlete_id, surface, created_at);
            CREATE INDEX IF NOT EXISTS idx_narr_surface ON narrative_renders(surface, created_at);
            CREATE TABLE IF NOT EXISTS publications (
                id TEXT PRIMARY KEY,
                season_id TEXT REFERENCES seasons(id),
                athlete_id TEXT NOT NULL REFERENCES athletes(id),
                plan_artifact_id TEXT REFERENCES plan_artifacts(id),
                created_at TEXT NOT NULL,
                spreadsheet_id TEXT,
                sheet_title TEXT,
                url TEXT,
                engine_version TEXT,
                template_version TEXT,
                prompt_version TEXT,
                llm_model TEXT,
                narrative_source TEXT,
                rows_written INTEGER,
                meta_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (season_id) REFERENCES seasons(id),
                FOREIGN KEY (athlete_id) REFERENCES athletes(id),
                FOREIGN KEY (plan_artifact_id) REFERENCES plan_artifacts(id)
            );
            CREATE INDEX IF NOT EXISTS idx_pub_athlete ON publications(athlete_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_pub_artifact ON publications(plan_artifact_id);
            CREATE TABLE IF NOT EXISTS weekly_actuals (
                season_id TEXT NOT NULL REFERENCES seasons(id),
                athlete_id TEXT NOT NULL REFERENCES athletes(id),
                week_start TEXT NOT NULL,
                run_miles REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'strava',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (season_id, week_start),
                FOREIGN KEY (season_id) REFERENCES seasons(id),
                FOREIGN KEY (athlete_id) REFERENCES athletes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_weekly_actuals_athlete ON weekly_actuals(athlete_id, week_start);
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dossier_snapshots (
                id TEXT PRIMARY KEY,
                season_id TEXT REFERENCES seasons(id),
                athlete_id TEXT NOT NULL REFERENCES athletes(id),
                computed_at TEXT NOT NULL,
                dossier_version TEXT,
                inputs_fingerprint TEXT NOT NULL DEFAULT '',
                full_json TEXT NOT NULL,
                responder TEXT,
                demonstrated_opener_mpw REAL,
                peak_mpw REAL,
                sustainable_low_mpw REAL,
                sustainable_high_mpw REAL,
                volume_vdot_corr REAL,
                endurance_gap REAL,
                current_vdot REAL,
                anchor_age_days INTEGER,
                anchor_stale INTEGER,
                injury_prone INTEGER,
                FOREIGN KEY (season_id) REFERENCES seasons(id),
                FOREIGN KEY (athlete_id) REFERENCES athletes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_dossier_athlete ON dossier_snapshots(athlete_id, computed_at);
            CREATE INDEX IF NOT EXISTS idx_dossier_responder ON dossier_snapshots(responder, computed_at);
            """
        )
        self._migrate()
        self._conn.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")
        self._conn.commit()

    def _migrate(self) -> None:
        """Bring an existing DB file's tables up to the current schema. `CREATE TABLE IF NOT EXISTS`
        only creates missing tables, so column additions live here and run idempotently."""
        art_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(plan_artifacts)")}
        if "engine_version" not in art_cols:
            self._conn.execute("ALTER TABLE plan_artifacts ADD COLUMN engine_version TEXT")
        if "club_policy_version" not in art_cols:
            self._conn.execute("ALTER TABLE plan_artifacts ADD COLUMN club_policy_version TEXT")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_artifacts_engine ON plan_artifacts(engine_version)"
        )
        narr_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(narrative_renders)")}
        if narr_cols and "plan_artifact_id" not in narr_cols:
            self._conn.execute("ALTER TABLE narrative_renders ADD COLUMN plan_artifact_id TEXT")
        # Created here (not in the main script) so it follows the column add above on legacy DBs.
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_narr_artifact ON narrative_renders(plan_artifact_id)"
        )

    # ----------------------------------------------------------------- athletes
    def upsert_athlete(self, a: Athlete) -> None:
        self._conn.execute(
            """INSERT INTO athletes (id, strava_athlete_id, name, created_at, meta_json)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 strava_athlete_id=excluded.strava_athlete_id,
                 name=excluded.name,
                 meta_json=excluded.meta_json""",
            (a.id, a.strava_athlete_id, a.name, a.created_at, json.dumps(a.meta)),
        )
        if a.strava_athlete_id:
            self._adopt_orphan_training_blocks(a.id, str(a.strava_athlete_id))
        self._conn.commit()

    def _adopt_orphan_training_blocks(self, athlete_id: str, strava_id: str) -> int:
        """Re-home training blocks scraped *before* this athlete was linked to a Strava id.

        A pre-import scrape keys its block by the raw Strava id (see
        ``main.training_block_from_report``: "keys by the Strava id so a pre-import scrape isn't
        lost"). Until the block's ``athlete_id`` becomes the canonical slug, a slug-keyed lookup
        (``latest_training_block("kelly-hession")``) can't see it. Linking the athlete is exactly
        when that adoption should happen. Idempotent: once re-keyed, the orphan filter no longer
        matches. Returns the number of blocks adopted."""
        if not strava_id or athlete_id == strava_id:
            return 0
        orphans = self._conn.execute(
            "SELECT id, marathon_date FROM training_blocks WHERE athlete_id = ?",
            (strava_id,),
        ).fetchall()
        adopted = 0
        for r in orphans:
            new_id = f"{athlete_id}:{r['marathon_date']}" if r["marathon_date"] else r["id"]
            if new_id != r["id"] and self._conn.execute(
                "SELECT 1 FROM training_blocks WHERE id = ?", (new_id,)
            ).fetchone():
                # A canonical row already exists for this marathon — drop the stale orphan.
                self._conn.execute("DELETE FROM training_blocks WHERE id = ?", (r["id"],))
            else:
                self._conn.execute(
                    "UPDATE training_blocks SET id = ?, athlete_id = ? WHERE id = ?",
                    (new_id, athlete_id, r["id"]),
                )
            adopted += 1
        return adopted

    def get_athlete(self, athlete_id: str) -> Athlete | None:
        row = self._conn.execute("SELECT * FROM athletes WHERE id = ?", (athlete_id,)).fetchone()
        if not row:
            return None
        return Athlete(
            id=row["id"],
            strava_athlete_id=row["strava_athlete_id"],
            name=row["name"],
            created_at=row["created_at"],
            meta=json.loads(row["meta_json"] or "{}"),
        )

    def list_athletes(self) -> list[Athlete]:
        rows = self._conn.execute(
            "SELECT * FROM athletes ORDER BY created_at, rowid"
        ).fetchall()
        return [
            Athlete(
                id=r["id"],
                strava_athlete_id=r["strava_athlete_id"],
                name=r["name"],
                created_at=r["created_at"],
                meta=json.loads(r["meta_json"] or "{}"),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ seasons
    def _season_from_row(self, row: sqlite3.Row) -> Season:
        return Season(
            id=row["id"],
            athlete_id=row["athlete_id"],
            label=row["label"],
            race_date=row["race_date"],
            status=row["status"],
            created_at=row["created_at"],
            meta=json.loads(row["meta_json"] or "{}"),
        )

    def create_season(self, season: Season, *, make_active: bool = True) -> str:
        """Insert a season. When ``make_active`` any other active season for the athlete is
        archived so exactly one season stays active."""
        if make_active:
            self._conn.execute(
                "UPDATE seasons SET status='archived' WHERE athlete_id=? AND status='active'",
                (season.athlete_id,),
            )
            season = season.model_copy(update={"status": "active"})
        self._conn.execute(
            """INSERT INTO seasons (id, athlete_id, label, race_date, status, created_at, meta_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                season.id,
                season.athlete_id,
                season.label,
                season.race_date,
                season.status,
                season.created_at,
                json.dumps(season.meta),
            ),
        )
        self._conn.commit()
        return season.id

    def get_season(self, season_id: str) -> Season | None:
        row = self._conn.execute("SELECT * FROM seasons WHERE id = ?", (season_id,)).fetchone()
        return self._season_from_row(row) if row else None

    def list_seasons(self, athlete_id: str) -> list[Season]:
        rows = self._conn.execute(
            "SELECT * FROM seasons WHERE athlete_id = ? ORDER BY created_at, rowid", (athlete_id,)
        ).fetchall()
        return [self._season_from_row(r) for r in rows]

    def get_active_season(self, athlete_id: str) -> Season | None:
        row = self._conn.execute(
            """SELECT * FROM seasons WHERE athlete_id = ? AND status = 'active'
               ORDER BY created_at DESC, rowid DESC LIMIT 1""",
            (athlete_id,),
        ).fetchone()
        return self._season_from_row(row) if row else None

    def set_active_season(self, season_id: str) -> None:
        season = self.get_season(season_id)
        if season is None:
            raise ValueError(f"no season {season_id!r}")
        self._conn.execute(
            "UPDATE seasons SET status='archived' WHERE athlete_id=? AND status='active' AND id<>?",
            (season.athlete_id, season_id),
        )
        self._conn.execute("UPDATE seasons SET status='active' WHERE id=?", (season_id,))
        self._conn.commit()

    def archive_season(self, season_id: str) -> None:
        self._conn.execute("UPDATE seasons SET status='archived' WHERE id=?", (season_id,))
        self._conn.commit()

    def ensure_active_season(
        self, athlete_id: str, *, label: str | None = None, race_date: str | None = None
    ) -> Season:
        existing = self.get_active_season(athlete_id)
        if existing is not None:
            return existing
        season = Season(
            athlete_id=athlete_id,
            label=label or "Season 1",
            race_date=race_date,
            status="active",
        )
        self.create_season(season, make_active=True)
        return season

    def _resolve_write_season(
        self, athlete_id: str, season_id: str | None, *, label: str | None = None, race_date: str | None = None
    ) -> str:
        if season_id:
            return season_id
        return self.ensure_active_season(athlete_id, label=label, race_date=race_date).id

    def _resolve_read_season(self, athlete_id: str, season_id: str | None) -> str | None:
        if season_id:
            return season_id
        active = self.get_active_season(athlete_id)
        return active.id if active else None

    # --------------------------------------------------------- survey baselines
    def save_survey_baseline(
        self, athlete_id: str, survey: SurveyInputs, *, season_id: str | None = None
    ) -> None:
        sid = self._resolve_write_season(
            athlete_id,
            season_id,
            label=f"{survey.race_name} {survey.race_date}".strip(),
            race_date=survey.race_date,
        )
        self._conn.execute(
            """INSERT INTO survey_baselines (season_id, athlete_id, updated_at, payload_json)
               VALUES (?, ?, datetime('now'), ?)
               ON CONFLICT(season_id) DO UPDATE SET
                 updated_at=datetime('now'),
                 payload_json=excluded.payload_json""",
            (sid, athlete_id, survey.model_dump_json()),
        )
        self._conn.commit()

    def load_survey_baseline(
        self, athlete_id: str, *, season_id: str | None = None
    ) -> SurveyInputs | None:
        sid = self._resolve_read_season(athlete_id, season_id)
        if sid is None:
            return None
        row = self._conn.execute(
            "SELECT payload_json FROM survey_baselines WHERE season_id = ?",
            (sid,),
        ).fetchone()
        if not row:
            return None
        return SurveyInputs.model_validate_json(row["payload_json"])

    # ------------------------------------------------------------------- events
    def append_event(
        self,
        event_id: str,
        athlete_id: str,
        ts: str,
        source: str,
        status: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        season_id: str | None = None,
    ) -> None:
        sid = self._resolve_write_season(athlete_id, season_id)
        self._conn.execute(
            """INSERT INTO events (id, season_id, athlete_id, ts, source, status, event_type, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, sid, athlete_id, ts, source, status, event_type, json.dumps(payload)),
        )
        self._conn.commit()

    def append_event_record(self, ev: Any, *, season_id: str | None = None) -> None:
        """Persist a validated :class:`store.events.EventRecord`."""
        from .events import event_type_name

        self.append_event(
            ev.id,
            ev.athlete_id,
            ev.ts,
            ev.source,
            ev.status,
            event_type_name(ev.payload),
            ev.payload.model_dump(mode="json"),
            season_id=season_id,
        )

    def list_events(
        self, athlete_id: str, *, status: str | None = None, season_id: str | None = None
    ) -> list[sqlite3.Row]:
        sid = self._resolve_read_season(athlete_id, season_id)
        if sid is None:
            return []
        if status:
            return list(
                self._conn.execute(
                    "SELECT * FROM events WHERE season_id = ? AND status = ? ORDER BY ts",
                    (sid, status),
                )
            )
        return list(
            self._conn.execute(
                "SELECT * FROM events WHERE season_id = ? ORDER BY ts", (sid,)
            )
        )

    def update_event_status(self, event_id: str, status: str) -> None:
        self._conn.execute("UPDATE events SET status = ? WHERE id = ?", (status, event_id))
        self._conn.commit()

    # ------------------------------------------------------------ plan artifacts
    def save_plan_artifact(
        self,
        athlete_id: str,
        plan: TrainingPlan,
        inputs_hash: str,
        *,
        season_id: str | None = None,
        resolved_inputs: AthleteInputs | None = None,
        engine_version: str | None = None,
        club_policy_version: str | None = None,
    ) -> str:
        from engine.plan import ENGINE_VERSION
        from engine.plan.club import ClubPolicy

        sid = self._resolve_write_season(athlete_id, season_id)
        pid = str(uuid.uuid4())
        body = training_plan_to_dict(plan)
        resolved_json = (
            json.dumps(athlete_inputs_to_dict(resolved_inputs)) if resolved_inputs is not None else None
        )
        policy_v = club_policy_version if club_policy_version is not None else str(ClubPolicy().version)
        self._conn.execute(
            """INSERT INTO plan_artifacts
                 (id, season_id, athlete_id, created_at, inputs_hash, plan_json,
                  resolved_inputs_json, engine_version, club_policy_version)
               VALUES (?, ?, ?, datetime('now'), ?, ?, ?, ?, ?)""",
            (
                pid, sid, athlete_id, inputs_hash, json.dumps(body), resolved_json,
                engine_version or ENGINE_VERSION, policy_v,
            ),
        )
        self._conn.commit()
        return pid

    def load_latest_plan(
        self, athlete_id: str, *, season_id: str | None = None
    ) -> PlanArtifact | None:
        sid = self._resolve_read_season(athlete_id, season_id)
        if sid is None:
            return None
        row = self._conn.execute(
            """SELECT * FROM plan_artifacts WHERE season_id = ?
               ORDER BY created_at DESC, rowid DESC LIMIT 1""",
            (sid,),
        ).fetchone()
        if not row:
            return None
        return self._artifact_from_row(row)

    def _artifact_from_row(self, row: sqlite3.Row) -> PlanArtifact:
        resolved_raw = row["resolved_inputs_json"]
        keys = row.keys()
        return PlanArtifact(
            id=row["id"],
            athlete_id=row["athlete_id"],
            season_id=row["season_id"],
            created_at=row["created_at"],
            inputs_hash=row["inputs_hash"],
            plan_json=json.loads(row["plan_json"]),
            resolved_inputs=json.loads(resolved_raw) if resolved_raw else None,
            engine_version=row["engine_version"],
            club_policy_version=row["club_policy_version"] if "club_policy_version" in keys else None,
        )

    def list_plan_artifacts(
        self, athlete_id: str | None = None, *, season_id: str | None = None, limit: int | None = None
    ) -> list[PlanArtifact]:
        """Plan artifacts newest-first. No ``athlete_id`` → across the whole fleet (engine/policy
        attribution analysis). ``season_id`` narrows to one season when given."""
        clauses: list[str] = []
        params: list[Any] = []
        if athlete_id:
            clauses.append("athlete_id = ?")
            params.append(athlete_id)
        if season_id:
            clauses.append("season_id = ?")
            params.append(season_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM plan_artifacts {where} ORDER BY created_at DESC, rowid DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return [self._artifact_from_row(r) for r in self._conn.execute(sql, tuple(params))]

    def plan_from_artifact(self, art: PlanArtifact) -> TrainingPlan:
        return training_plan_from_dict(art.plan_json)

    # ---------------------------------------------------------- training blocks
    def get_athlete_by_strava(self, strava_athlete_id: str) -> Athlete | None:
        row = self._conn.execute(
            "SELECT * FROM athletes WHERE strava_athlete_id = ? LIMIT 1",
            (str(strava_athlete_id),),
        ).fetchone()
        if not row:
            return None
        return Athlete(
            id=row["id"],
            strava_athlete_id=row["strava_athlete_id"],
            name=row["name"],
            created_at=row["created_at"],
            meta=json.loads(row["meta_json"] or "{}"),
        )

    @staticmethod
    def training_block_id(athlete_id: str, marathon_date: str | None) -> str:
        """Deterministic id per (athlete, marathon) so a re-scrape refreshes one row; a block with
        no detected marathon falls back to a fresh uuid (always appended)."""
        return f"{athlete_id}:{marathon_date}" if marathon_date else str(uuid.uuid4())

    def save_training_block(self, block: TrainingBlock) -> str:
        """Upsert a historical training-block snapshot (append-only across distinct marathons)."""
        self._conn.execute(
            """INSERT INTO training_blocks
                 (id, athlete_id, strava_athlete_id, source, scraped_at, marathon_date,
                  marathon_name, marathon_time_s, block_start, block_end, weeks_json,
                  report_json, profile_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 strava_athlete_id=excluded.strava_athlete_id,
                 source=excluded.source,
                 scraped_at=excluded.scraped_at,
                 marathon_name=excluded.marathon_name,
                 marathon_time_s=excluded.marathon_time_s,
                 block_start=excluded.block_start,
                 block_end=excluded.block_end,
                 weeks_json=excluded.weeks_json,
                 report_json=excluded.report_json,
                 profile_json=excluded.profile_json""",
            (
                block.id,
                block.athlete_id,
                block.strava_athlete_id,
                block.source,
                block.scraped_at,
                block.marathon_date,
                block.marathon_name,
                block.marathon_time_s,
                block.block_start,
                block.block_end,
                json.dumps(block.weeks, ensure_ascii=False),
                json.dumps(block.report, ensure_ascii=False) if block.report is not None else None,
                json.dumps(block.profile, ensure_ascii=False),
            ),
        )
        self._conn.commit()
        return block.id

    def _training_block_from_row(self, row: sqlite3.Row) -> TrainingBlock:
        return TrainingBlock(
            id=row["id"],
            athlete_id=row["athlete_id"],
            strava_athlete_id=row["strava_athlete_id"],
            source=row["source"],
            scraped_at=row["scraped_at"],
            marathon_date=row["marathon_date"],
            marathon_name=row["marathon_name"],
            marathon_time_s=row["marathon_time_s"],
            block_start=row["block_start"],
            block_end=row["block_end"],
            weeks=json.loads(row["weeks_json"]) if row["weeks_json"] else [],
            report=json.loads(row["report_json"]) if row["report_json"] else None,
            profile=json.loads(row["profile_json"]) if row["profile_json"] else {},
        )

    def list_training_blocks(self, athlete_or_strava_id: str) -> list[TrainingBlock]:
        """All stored blocks for an athlete, newest marathon first. Matches either the store
        ``athlete_id`` or the ``strava_athlete_id`` so callers can use whichever they hold."""
        key = str(athlete_or_strava_id)
        rows = self._conn.execute(
            """SELECT * FROM training_blocks
               WHERE athlete_id = ? OR strava_athlete_id = ?
               ORDER BY marathon_date DESC, scraped_at DESC""",
            (key, key),
        ).fetchall()
        return [self._training_block_from_row(r) for r in rows]

    def latest_training_block(self, athlete_or_strava_id: str) -> TrainingBlock | None:
        blocks = self.list_training_blocks(athlete_or_strava_id)
        return blocks[0] if blocks else None

    def get_training_block(self, block_id: str) -> TrainingBlock | None:
        row = self._conn.execute(
            "SELECT * FROM training_blocks WHERE id = ?", (block_id,)
        ).fetchone()
        return self._training_block_from_row(row) if row else None

    # ------------------------------------------------------- narrative renders
    def append_narrative_render(self, rec: Any, *, season_id: str | None = None) -> None:
        """Persist one `engine.narrative_capture.NarrativeRender` (append-only observability log).

        Season is resolved like other writes when ``rec.season_id`` is unset. Capture is provenance,
        not plan state — callers treat failures as non-fatal so rendering never breaks on logging."""
        sid = season_id or rec.season_id or self._resolve_write_season(rec.athlete_id, None)
        self._conn.execute(
            """INSERT INTO narrative_renders
               (id, season_id, athlete_id, created_at, surface, template_version, prompt_version,
                llm_model, source, deterministic_text, final_text, changed, char_delta, guard_passed,
                signals_json, inputs_fingerprint, plan_artifact_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                sid,
                rec.athlete_id,
                rec.created_at,
                rec.surface,
                rec.template_version,
                rec.prompt_version,
                rec.llm_model,
                rec.source,
                rec.deterministic_text,
                rec.final_text,
                1 if rec.changed else 0,
                int(rec.char_delta),
                1 if rec.guard_passed else 0,
                json.dumps(rec.signals, ensure_ascii=False),
                rec.inputs_fingerprint,
                getattr(rec, "plan_artifact_id", None),
            ),
        )
        self._conn.commit()

    def list_narrative_renders(
        self, athlete_id: str | None = None, *, surface: str | None = None, limit: int | None = None
    ) -> list[sqlite3.Row]:
        """Captured renders newest-first. No ``athlete_id`` → across all athletes (fleet-wide analysis)."""
        clauses: list[str] = []
        params: list[Any] = []
        if athlete_id:
            clauses.append("athlete_id = ?")
            params.append(athlete_id)
        if surface:
            clauses.append("surface = ?")
            params.append(surface)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM narrative_renders {where} ORDER BY created_at DESC, rowid DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return list(self._conn.execute(sql, tuple(params)))

    # ------------------------------------------------------------- publications
    def record_publication(self, pub: Publication, *, season_id: str | None = None) -> str:
        """Append a record that ``pub.plan_artifact_id`` was published to a sheet (lineage log).

        Season is resolved like other writes when ``pub.season_id`` is unset. Append-only and
        best-effort at the call site — a logging failure must never fail an actual publish."""
        sid = season_id or pub.season_id or self._resolve_write_season(pub.athlete_id, None)
        pid = pub.id or str(uuid.uuid4())
        self._conn.execute(
            """INSERT INTO publications
               (id, season_id, athlete_id, plan_artifact_id, created_at, spreadsheet_id, sheet_title,
                url, engine_version, template_version, prompt_version, llm_model, narrative_source,
                rows_written, meta_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pid,
                sid,
                pub.athlete_id,
                pub.plan_artifact_id,
                pub.created_at,
                pub.spreadsheet_id,
                pub.sheet_title,
                pub.url,
                pub.engine_version,
                pub.template_version,
                pub.prompt_version,
                pub.llm_model,
                pub.narrative_source,
                pub.rows_written,
                json.dumps(pub.meta, ensure_ascii=False),
            ),
        )
        self._conn.commit()
        return pid

    def list_publications(
        self, athlete_id: str | None = None, *, plan_artifact_id: str | None = None,
        limit: int | None = None,
    ) -> list[sqlite3.Row]:
        """Publications newest-first. Filter by athlete and/or the plan artifact they published."""
        clauses: list[str] = []
        params: list[Any] = []
        if athlete_id:
            clauses.append("athlete_id = ?")
            params.append(athlete_id)
        if plan_artifact_id:
            clauses.append("plan_artifact_id = ?")
            params.append(plan_artifact_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM publications {where} ORDER BY created_at DESC, rowid DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return list(self._conn.execute(sql, tuple(params)))

    # ----------------------------------------------------------- weekly actuals
    def upsert_weekly_actuals(
        self, athlete_id: str, weekly: dict[str, float], *,
        season_id: str | None = None, source: str = "strava",
    ) -> int:
        """Persist per-week actual run miles (``week_start`` ISO Monday → miles) for the season, so
        execution scoring (`engine.execution.execution_from_actuals`) is replayable from the store
        without the training feed file. Upsert keyed by ``(season, week_start)`` — a re-scrape
        refreshes a week rather than duplicating it. Returns the number of weeks written."""
        sid = self._resolve_write_season(athlete_id, season_id)
        rows = [
            (sid, athlete_id, str(ws), float(mi), source)
            for ws, mi in weekly.items()
            if ws
        ]
        self._conn.executemany(
            """INSERT INTO weekly_actuals (season_id, athlete_id, week_start, run_miles, source, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(season_id, week_start) DO UPDATE SET
                 run_miles=excluded.run_miles, source=excluded.source, updated_at=excluded.updated_at""",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def load_weekly_actuals(
        self, athlete_id: str, *, season_id: str | None = None
    ) -> dict[str, float]:
        """Stored per-week actual run miles for the season as ``week_start`` → miles. Empty when the
        season is unknown or nothing has been persisted yet."""
        sid = self._resolve_read_season(athlete_id, season_id)
        if sid is None:
            return {}
        rows = self._conn.execute(
            "SELECT week_start, run_miles FROM weekly_actuals WHERE season_id = ? ORDER BY week_start",
            (sid,),
        )
        return {r["week_start"]: float(r["run_miles"]) for r in rows}

    # ------------------------------------------------------------------- config
    def set_config(self, key: str, value: Any) -> None:
        """Upsert a JSON-serializable value under ``key`` in the global (club-wide) config kv."""
        self._conn.execute(
            """INSERT INTO config (key, value_json, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET
                 value_json=excluded.value_json, updated_at=excluded.updated_at""",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self._conn.commit()

    def get_config(self, key: str) -> Any | None:
        """The value stored under ``key`` (JSON-decoded), or None when unset."""
        row = self._conn.execute(
            "SELECT value_json FROM config WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row["value_json"]) if row else None

    # -------------------------------------------------------- dossier snapshots
    def append_dossier_snapshot(self, snap: DossierSnapshot, *, season_id: str | None = None) -> str:
        """Append one `DossierSnapshot` (observability/accumulation log).

        Season is resolved like other writes when ``snap.season_id`` is unset. Append-only and
        best-effort at the call site — capture must never fail an actual report/publish."""
        sid = season_id or snap.season_id or self._resolve_write_season(snap.athlete_id, None)
        sid_val = snap.id or str(uuid.uuid4())
        self._conn.execute(
            """INSERT INTO dossier_snapshots
               (id, season_id, athlete_id, computed_at, dossier_version, inputs_fingerprint, full_json,
                responder, demonstrated_opener_mpw, peak_mpw, sustainable_low_mpw, sustainable_high_mpw,
                volume_vdot_corr, endurance_gap, current_vdot, anchor_age_days, anchor_stale, injury_prone)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sid_val,
                sid,
                snap.athlete_id,
                snap.computed_at,
                snap.dossier_version,
                snap.inputs_fingerprint,
                json.dumps(snap.full_json, ensure_ascii=False),
                snap.responder,
                snap.demonstrated_opener_mpw,
                snap.peak_mpw,
                snap.sustainable_low_mpw,
                snap.sustainable_high_mpw,
                snap.volume_vdot_corr,
                snap.endurance_gap,
                snap.current_vdot,
                snap.anchor_age_days,
                None if snap.anchor_stale is None else (1 if snap.anchor_stale else 0),
                None if snap.injury_prone is None else (1 if snap.injury_prone else 0),
            ),
        )
        self._conn.commit()
        return sid_val

    def list_dossier_snapshots(
        self, athlete_id: str | None = None, *, limit: int | None = None
    ) -> list[sqlite3.Row]:
        """Dossier snapshots newest-first. No ``athlete_id`` → across all athletes (fleet analysis)."""
        clauses: list[str] = []
        params: list[Any] = []
        if athlete_id:
            clauses.append("athlete_id = ?")
            params.append(athlete_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM dossier_snapshots {where} ORDER BY computed_at DESC, rowid DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return list(self._conn.execute(sql, tuple(params)))


def fingerprint_athlete_inputs(inputs: Any) -> str:
    return athlete_inputs_fingerprint(inputs)
