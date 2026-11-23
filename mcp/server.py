"""Detour Engine — Headless Model Context Protocol (MCP) Server Stub.

Exposes deterministic training plan generation, continuous VDOT/pace calculation,
and event-sourced replanning to external agents (Claude, ChatGPT, etc.).
"""

from typing import Any, Dict, List, Optional


def detour_calculate_paces(vdot: float) -> Dict[str, Any]:
    """Calculate continuous training paces from VDOT using Daniels-Gilbert (1979)."""
    from engine.paces import training_paces
    return training_paces(vdot)


def detour_build_plan(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic training plan builder."""
    raise NotImplementedError("MCP server integration is scheduled for Phase 4.")


def detour_replan(athlete_id: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Event-sourced replan fold."""
    raise NotImplementedError("MCP server integration is scheduled for Phase 4.")
