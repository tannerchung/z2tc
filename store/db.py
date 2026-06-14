"""Thin SQLite persistence (no ORM). DB file under ``output/z2tc.db`` by default."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from engine.plan.models import TrainingPlan

from .models import Athlete, PlanArtifact, SurveyInputs
from .serialization import athlete_inputs_fingerprint, training_plan_from_dict, training_plan_to_dict


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
            CREATE TABLE IF NOT EXISTS survey_baselines (
                athlete_id TEXT PRIMARY KEY REFERENCES athletes(id),
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                FOREIGN KEY (athlete_id) REFERENCES athletes(id)
            );
            CREATE TABLE IF NOT EXISTS plan_artifacts (
                id TEXT PRIMARY KEY,
                athlete_id TEXT NOT NULL REFERENCES athletes(id),
                created_at TEXT NOT NULL,
                inputs_hash TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                FOREIGN KEY (athlete_id) REFERENCES athletes(id)
            );
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                athlete_id TEXT NOT NULL REFERENCES athletes(id),
                ts TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                FOREIGN KEY (athlete_id) REFERENCES athletes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_events_athlete ON events(athlete_id, ts);
            """
        )
        self._conn.commit()

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
        self._conn.commit()

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

    def save_survey_baseline(self, athlete_id: str, survey: SurveyInputs) -> None:
        self._conn.execute(
            """INSERT INTO survey_baselines (athlete_id, updated_at, payload_json)
               VALUES (?, datetime('now'), ?)
               ON CONFLICT(athlete_id) DO UPDATE SET
                 updated_at=datetime('now'),
                 payload_json=excluded.payload_json""",
            (athlete_id, survey.model_dump_json()),
        )
        self._conn.commit()

    def load_survey_baseline(self, athlete_id: str) -> SurveyInputs | None:
        row = self._conn.execute(
            "SELECT payload_json FROM survey_baselines WHERE athlete_id = ?",
            (athlete_id,),
        ).fetchone()
        if not row:
            return None
        return SurveyInputs.model_validate_json(row["payload_json"])

    def append_event(
        self,
        event_id: str,
        athlete_id: str,
        ts: str,
        source: str,
        status: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        self._conn.execute(
            """INSERT INTO events (id, athlete_id, ts, source, status, event_type, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_id, athlete_id, ts, source, status, event_type, json.dumps(payload)),
        )
        self._conn.commit()

    def append_event_record(self, ev: Any) -> None:
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
        )

    def list_events(self, athlete_id: str, *, status: str | None = None) -> list[sqlite3.Row]:
        if status:
            return list(
                self._conn.execute(
                    "SELECT * FROM events WHERE athlete_id = ? AND status = ? ORDER BY ts",
                    (athlete_id, status),
                )
            )
        return list(
            self._conn.execute(
                "SELECT * FROM events WHERE athlete_id = ? ORDER BY ts", (athlete_id,)
            )
        )

    def update_event_status(self, event_id: str, status: str) -> None:
        self._conn.execute("UPDATE events SET status = ? WHERE id = ?", (status, event_id))
        self._conn.commit()

    def save_plan_artifact(self, athlete_id: str, plan: TrainingPlan, inputs_hash: str) -> str:
        import uuid

        pid = str(uuid.uuid4())
        body = training_plan_to_dict(plan)
        self._conn.execute(
            """INSERT INTO plan_artifacts (id, athlete_id, created_at, inputs_hash, plan_json)
               VALUES (?, ?, datetime('now'), ?, ?)""",
            (pid, athlete_id, inputs_hash, json.dumps(body)),
        )
        self._conn.commit()
        return pid

    def load_latest_plan(self, athlete_id: str) -> PlanArtifact | None:
        row = self._conn.execute(
            """SELECT * FROM plan_artifacts WHERE athlete_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (athlete_id,),
        ).fetchone()
        if not row:
            return None
        return PlanArtifact(
            id=row["id"],
            athlete_id=row["athlete_id"],
            created_at=row["created_at"],
            inputs_hash=row["inputs_hash"],
            plan_json=json.loads(row["plan_json"]),
        )

    def plan_from_artifact(self, art: PlanArtifact) -> TrainingPlan:
        return training_plan_from_dict(art.plan_json)


def fingerprint_athlete_inputs(inputs: Any) -> str:
    return athlete_inputs_fingerprint(inputs)
