"""Integration: Kelly survey fixture → build-plan → replan → monitor (temp SQLite)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from store.db import Store

REPO = Path(__file__).resolve().parents[1]
MAIN = REPO / "main.py"
SURVEY = REPO / "tests" / "fixtures" / "survey_kelly.json"


@pytest.mark.skipif(not SURVEY.exists(), reason="survey fixture missing")
def test_kelly_build_replan_monitor_cli(tmp_path: Path) -> None:
    db = tmp_path / "kelly.db"
    training = tmp_path / "weeks.jsonl"
    training.write_text("", encoding="utf-8")
    athlete_id = "kelly-test"

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(MAIN), *args, "--db", str(db)],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=120,
        )

    r1 = run("build-plan", athlete_id, "--survey", str(SURVEY))
    assert r1.returncode == 0, r1.stdout + r1.stderr
    r2 = run("replan", athlete_id)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    r3 = run("monitor", athlete_id, "--training", str(training))
    assert r3.returncode == 0, r3.stdout + r3.stderr
    assert "AdherenceFlag" in r3.stdout
    assert "Logged 18 monitor" in r3.stdout


@pytest.mark.skipif(not SURVEY.exists(), reason="survey fixture missing")
def test_kelly_hitl_propose_review_subprocess(tmp_path: Path) -> None:
    """Subprocess wiring: build-plan → propose-notes (stub LLM) → review --yes-all."""
    db = tmp_path / "kelly_hitl.db"
    athlete_id = "kelly-hitl-cli"
    stub = json.dumps(
        [
            {
                "kind": "WeeklyEvaluation",
                "week_start": "2026-06-01",
                "calibrated_vdot": 51.0,
                "note": "stub subprocess",
            }
        ]
    )
    env = {
        **os.environ,
        "Z2TC_DISABLE_GEMINI": "1",
        "Z2TC_LLM_STUB_EVENTS_JSON": stub,
    }

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(MAIN), *args, "--db", str(db)],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

    r0 = run("build-plan", athlete_id, "--survey", str(SURVEY))
    assert r0.returncode == 0, r0.stdout + r0.stderr
    r1 = run(
        "propose-notes",
        athlete_id,
        "--text",
        "Calibration note from coach for subprocess test.",
    )
    assert r1.returncode == 0, r1.stdout + r1.stderr
    assert "proposed WeeklyEvaluation" in r1.stdout
    r2 = run("review", athlete_id, "--yes-all")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "Saved replan artifact" in r2.stdout
    st = Store(db_path=db, project_root=tmp_path)
    art = st.load_latest_plan(athlete_id)
    assert art is not None
    assert float(art.plan_json.get("vdot", 0.0)) == pytest.approx(51.0)
