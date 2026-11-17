"""Dual-backend (local SQLite FTS5 + Supabase Postgres SECURITY INVOKER RPC)
Context Assembler for Detour Athletics coaching workflows."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any


class CoachingContextAssembler:
    """Assembles athlete-isolated, authority-weighted coaching context."""

    def __init__(self, sqlite_path: Path | str | None = None) -> None:
        self._sqlite_path = Path(sqlite_path) if sqlite_path is not None else None
        self._conn: sqlite3.Connection | None = None
        if self._sqlite_path is not None:
            self._conn = sqlite3.connect(str(self._sqlite_path))
            self._conn.row_factory = sqlite3.Row

    def init_sqlite_schema(self) -> None:
        if self._conn is None:
            raise RuntimeError("SQLite connection not configured")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS coach_doctrine_docs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                body_md TEXT NOT NULL,
                visibility TEXT NOT NULL DEFAULT 'club_public',
                doc_priority REAL NOT NULL DEFAULT 1.25,
                entity_tags_json TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS athlete_dossiers (
                athlete_id TEXT PRIMARY KEY,
                compiled_truth_md TEXT NOT NULL DEFAULT '',
                structured_facts_json TEXT NOT NULL DEFAULT '{}',
                visibility TEXT NOT NULL DEFAULT 'athlete_visible'
            );

            CREATE TABLE IF NOT EXISTS athlete_events (
                id TEXT PRIMARY KEY,
                athlete_id TEXT NOT NULL,
                event_kind TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                visibility TEXT NOT NULL DEFAULT 'athlete_visible',
                doc_priority REAL NOT NULL DEFAULT 0.90,
                entity_tags_json TEXT NOT NULL DEFAULT '[]'
            );
            """
        )
        self._conn.commit()

    def upsert_doctrine_doc(
        self,
        *,
        doc_id: str,
        title: str,
        body_md: str,
        visibility: str = "club_public",
        doc_priority: float = 1.25,
        entity_tags: list[str] | None = None,
    ) -> None:
        assert self._conn is not None
        self._conn.execute(
            """
            INSERT OR REPLACE INTO coach_doctrine_docs
            (id, title, body_md, visibility, doc_priority, entity_tags_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (doc_id, title, body_md, visibility, doc_priority, json.dumps(entity_tags or [])),
        )
        self._conn.commit()

    def upsert_dossier(
        self,
        *,
        athlete_id: str,
        compiled_truth_md: str,
        structured_facts: dict[str, Any] | None = None,
        visibility: str = "athlete_visible",
    ) -> None:
        assert self._conn is not None
        self._conn.execute(
            """
            INSERT OR REPLACE INTO athlete_dossiers
            (athlete_id, compiled_truth_md, structured_facts_json, visibility)
            VALUES (?, ?, ?, ?)
            """,
            (athlete_id, compiled_truth_md, json.dumps(structured_facts or {}), visibility),
        )
        self._conn.commit()

    def insert_athlete_event(
        self,
        *,
        event_id: str,
        athlete_id: str,
        event_kind: str,
        summary_text: str,
        visibility: str = "athlete_visible",
        doc_priority: float = 0.90,
        entity_tags: list[str] | None = None,
    ) -> None:
        assert self._conn is not None
        self._conn.execute(
            """
            INSERT OR REPLACE INTO athlete_events
            (id, athlete_id, event_kind, summary_text, visibility, doc_priority, entity_tags_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                athlete_id,
                event_kind,
                summary_text,
                visibility,
                doc_priority,
                json.dumps(entity_tags or []),
            ),
        )
        self._conn.commit()

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {tok for tok in re.findall(r"[a-z0-9_]+", text.lower()) if len(tok) >= 2}

    def assemble_context(
        self,
        *,
        query: str,
        target_athlete_id: str,
        caller_id: str,
        caller_role: str = "athlete",
        required_entity_tags: list[str] | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Early-binding principal + visibility filter mirrored to local SQLite."""
        assert self._conn is not None
        is_coach = caller_role in ("coach", "admin")

        if not is_coach and caller_id != target_athlete_id:
            return {"athlete_id": target_athlete_id, "dossier": None, "items": []}

        allowed_vis = (
            ("club_public", "athlete_visible", "coach_internal")
            if is_coach
            else ("club_public", "athlete_visible")
        )

        dossier_row = self._conn.execute(
            """
            SELECT athlete_id, compiled_truth_md, structured_facts_json, visibility
            FROM athlete_dossiers
            WHERE athlete_id = ?
            """,
            (target_athlete_id,),
        ).fetchone()

        dossier: dict[str, Any] | None = None
        if dossier_row is not None and dossier_row["visibility"] in allowed_vis:
            dossier = {
                "athlete_id": dossier_row["athlete_id"],
                "compiled_truth_md": dossier_row["compiled_truth_md"],
                "structured_facts": json.loads(dossier_row["structured_facts_json"]),
            }

        q_tokens = self._tokenize(query)
        req_tags = set(required_entity_tags or [])
        candidates: list[dict[str, Any]] = []

        # 1. Coach doctrine candidates (early-filtered by visibility)
        placeholders = ",".join("?" for _ in allowed_vis)
        for row in self._conn.execute(
            f"SELECT * FROM coach_doctrine_docs WHERE visibility IN ({placeholders})",
            allowed_vis,
        ):
            tags = set(json.loads(row["entity_tags_json"]))
            if req_tags and not req_tags.issubset(tags):
                continue
            doc_tokens = self._tokenize(f"{row['title']} {row['body_md']}")
            overlap = len(q_tokens & doc_tokens)
            if q_tokens and overlap == 0:
                continue
            score = (overlap + 0.1) * float(row["doc_priority"])
            candidates.append(
                {
                    "id": row["id"],
                    "source_type": "doctrine",
                    "title": row["title"],
                    "snippet": row["body_md"],
                    "visibility": row["visibility"],
                    "entity_tags": sorted(tags),
                    "score": round(score, 4),
                }
            )

        # 2. Target athlete's events (strictly bound to target_athlete_id + allowed_vis)
        for row in self._conn.execute(
            f"""
            SELECT * FROM athlete_events
            WHERE athlete_id = ? AND visibility IN ({placeholders})
            """,
            (target_athlete_id, *allowed_vis),
        ):
            tags = set(json.loads(row["entity_tags_json"]))
            if req_tags and not req_tags.issubset(tags):
                continue
            ev_tokens = self._tokenize(f"{row['event_kind']} {row['summary_text']}")
            overlap = len(q_tokens & ev_tokens)
            if q_tokens and overlap == 0:
                continue
            score = (overlap + 0.1) * float(row["doc_priority"])
            candidates.append(
                {
                    "id": row["id"],
                    "source_type": "athlete_event",
                    "title": row["event_kind"],
                    "snippet": row["summary_text"],
                    "visibility": row["visibility"],
                    "entity_tags": sorted(tags),
                    "score": round(score, 4),
                }
            )

        candidates.sort(key=lambda item: item["score"], reverse=True)
        return {
            "athlete_id": target_athlete_id,
            "dossier": dossier,
            "items": candidates[: max(1, min(limit, 25))],
        }

    @staticmethod
    def build_postgres_rpc_call(
        *,
        query: str,
        target_athlete_id: str,
        required_entity_tags: list[str] | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Builds parameterized Supabase PostgREST payload for coaching.assemble_coaching_context."""
        return {
            "schema": "coaching",
            "rpc_name": "assemble_coaching_context",
            "params": {
                "p_query": query,
                "p_athlete_id": target_athlete_id,
                "p_entity_tags": required_entity_tags,
                "p_limit": max(1, min(int(limit), 25)),
            },
        }
