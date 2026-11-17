"""Contract tests for Supabase coaching.* schema migration (009)."""

from __future__ import annotations

from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "009_coaching_ai_context_and_dossiers.sql"
)


def test_coaching_migration_enforces_rls_halfvec_and_2kb_cap() -> None:
    assert MIGRATION_PATH.exists(), f"Missing migration: {MIGRATION_PATH}"
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    # 1. Dedicated schema + 5 core tables
    assert "CREATE SCHEMA IF NOT EXISTS coaching;" in sql
    for table in (
        "coaching.coach_doctrine_docs",
        "coaching.athlete_dossiers",
        "coaching.athlete_events",
        "coaching.activity_compact_summaries",
        "coaching.coach_review_queue",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql, f"Missing {table}"
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in sql, f"RLS missing on {table}"

    # 2. Subscription-protecting storage invariants: halfvec(1536) + <= 2048-byte JSONB cap
    assert "halfvec(1536)" in sql
    assert "octet_length(compact_json::text) <= 2048" in sql

    # 3. Inverted GIN indexes for entity_tags & full-text tsv
    assert "USING GIN (entity_tags)" in sql
    assert "USING GIN (tsv)" in sql

    # 4. Visibility isolation + SECURITY INVOKER context RPC
    assert "coach_internal" in sql
    assert "athlete_visible" in sql
    assert "club_public" in sql
    assert "CREATE OR REPLACE FUNCTION coaching.assemble_coaching_context" in sql
    assert "SECURITY INVOKER" in sql
    assert "SECURITY DEFINER" not in sql
