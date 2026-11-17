"""Tests for dual-backend (SQLite + Supabase Postgres RPC) CoachingContextAssembler."""

from __future__ import annotations

from pathlib import Path

from engine.context_assembler import CoachingContextAssembler


def _seeded_assembler(tmp_path: Path) -> CoachingContextAssembler:
    asm = CoachingContextAssembler(sqlite_path=tmp_path / "coaching_ctx.db")
    asm.init_sqlite_schema()

    # Coach doctrine (club_public, priority 1.25) + internal coach rubric (coach_internal)
    asm.upsert_doctrine_doc(
        doc_id="doc-achilles-protocol",
        title="Achilles Tendon Return-to-Load Protocol",
        body_md="Reduce uphill tempo and monitor morning achilles stiffness for 48 hours.",
        visibility="club_public",
        doc_priority=1.25,
        entity_tags=["injury:achilles", "workout:tempo"],
    )
    asm.upsert_doctrine_doc(
        doc_id="doc-coach-private-escalation",
        title="Internal Coach Clinical Escalation Rubric",
        body_md="Refer achilles stiffness >= 4/5 to sports PT partner immediately.",
        visibility="coach_internal",
        doc_priority=1.30,
        entity_tags=["injury:achilles"],
    )

    # Athlete A vs Athlete B dossiers & events
    asm.upsert_dossier(
        athlete_id="athlete-a",
        compiled_truth_md="VDOT 48.2 | Maurten 100 | Mild right achilles morning stiffness.",
        structured_facts={"vdot": 48.2, "preferred_gel": "Maurten 100"},
    )
    asm.upsert_dossier(
        athlete_id="athlete-b",
        compiled_truth_md="VDOT 54.0 | Secret Athlete B Boston build.",
        structured_facts={"vdot": 54.0},
    )

    asm.insert_athlete_event(
        event_id="ev-a-1",
        athlete_id="athlete-a",
        event_kind="PainFlag",
        summary_text="Right achilles stiffness 2/5 on cooldown jog; fuel Maurten felt fine.",
        visibility="athlete_visible",
        doc_priority=0.90,
        entity_tags=["injury:achilles", "fuel:maurten"],
    )
    asm.insert_athlete_event(
        event_id="ev-a-internal",
        athlete_id="athlete-a",
        event_kind="CoachPrivateNote",
        summary_text="Coach private observation: watch achilles stiffness before Brooklyn Half.",
        visibility="coach_internal",
        doc_priority=1.10,
        entity_tags=["injury:achilles"],
    )
    asm.insert_athlete_event(
        event_id="ev-b-1",
        athlete_id="athlete-b",
        event_kind="PainFlag",
        summary_text="Athlete B achilles stiffness and fuel notes that must never leak.",
        visibility="athlete_visible",
        doc_priority=0.95,
        entity_tags=["injury:achilles"],
    )
    return asm


def test_athlete_isolation_and_doctrine_priority(tmp_path: Path) -> None:
    asm = _seeded_assembler(tmp_path)
    bundle = asm.assemble_context(
        query="achilles stiffness",
        target_athlete_id="athlete-a",
        caller_id="athlete-a",
        caller_role="athlete",
        limit=10,
    )

    assert bundle["dossier"] is not None
    assert "VDOT 48.2" in bundle["dossier"]["compiled_truth_md"]

    ids = [item["id"] for item in bundle["items"]]
    assert "doc-achilles-protocol" in ids
    assert "ev-a-1" in ids
    # Zero cross-athlete leakage + zero coach_internal leakage to athlete caller
    assert "ev-b-1" not in ids
    assert "ev-a-internal" not in ids
    assert "doc-coach-private-escalation" not in ids

    # Curated coach doctrine (priority 1.25) outranks raw event log (priority 0.90)
    assert ids.index("doc-achilles-protocol") < ids.index("ev-a-1")


def test_coach_role_unlocks_coach_internal_notes(tmp_path: Path) -> None:
    asm = _seeded_assembler(tmp_path)
    bundle = asm.assemble_context(
        query="achilles stiffness",
        target_athlete_id="athlete-a",
        caller_id="coach-tanner",
        caller_role="coach",
        limit=10,
    )
    ids = [item["id"] for item in bundle["items"]]
    assert "ev-a-internal" in ids
    assert "doc-coach-private-escalation" in ids
    assert "ev-b-1" not in ids


def test_entity_tag_filter_scopes_results(tmp_path: Path) -> None:
    asm = _seeded_assembler(tmp_path)
    bundle = asm.assemble_context(
        query="achilles",
        target_athlete_id="athlete-a",
        caller_id="athlete-a",
        caller_role="athlete",
        required_entity_tags=["fuel:maurten"],
        limit=10,
    )
    ids = [item["id"] for item in bundle["items"]]
    assert ids == ["ev-a-1"]


def test_postgres_rpc_payload_contract(tmp_path: Path) -> None:
    asm = _seeded_assembler(tmp_path)
    rpc = asm.build_postgres_rpc_call(
        query="marathon fuel",
        target_athlete_id="00000000-0000-0000-0000-000000000001",
        required_entity_tags=["fuel:maurten"],
        limit=6,
    )
    assert rpc["rpc_name"] == "assemble_coaching_context"
    assert rpc["schema"] == "coaching"
    assert rpc["params"] == {
        "p_query": "marathon fuel",
        "p_athlete_id": "00000000-0000-0000-0000-000000000001",
        "p_entity_tags": ["fuel:maurten"],
        "p_limit": 6,
    }
