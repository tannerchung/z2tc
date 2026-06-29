"""Phase 3 fleet/historical analytics: `dossier-log` and `plan-log` CLIs over the accumulated
snapshots + plan artifacts, plus the `club_policy_version` stamp and `list_plan_artifacts`."""

from __future__ import annotations

import argparse
from pathlib import Path

import main
from engine.plan import ENGINE_VERSION, build_plan
from engine.plan.club import ClubPolicy
from store.db import Store
from store.models import Athlete, DossierSnapshot


def _store(tmp_path: Path) -> Store:
    return Store(db_path=tmp_path / "s.db", project_root=tmp_path)


def _args(**kw) -> argparse.Namespace:
    base = {"db": None, "athlete_id": None, "limit": None, "json": False}
    base.update(kw)
    ns = argparse.Namespace(**base)
    return ns


def test_plan_artifact_stamps_policy_version(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.upsert_athlete(Athlete(id="ana", name="Ana"))
    plan = build_plan(main_inputs := _inputs())
    pid = s.save_plan_artifact("ana", plan, inputs_hash="h1")
    arts = s.list_plan_artifacts("ana")
    assert len(arts) == 1
    assert arts[0].id == pid
    assert arts[0].engine_version == ENGINE_VERSION
    assert arts[0].club_policy_version == str(ClubPolicy().version)


def _inputs():
    from engine.plan.models import AthleteInputs

    return AthleteInputs(
        name="Ana", vdot=50.0, goal_marathon_s=3 * 3600 + 30 * 60, w_now=35.0,
        p_history=40.0, longest_run_mi=16.0, days_per_week=5, race_date="2026-10-10",
    )


def test_dossier_log_empty_and_aggregate(tmp_path: Path, capsys) -> None:
    s = _store(tmp_path)
    # Empty scope.
    rc = main._cmd_dossier_log(_args(db=str(s.path)))
    assert rc == 0
    assert "No dossier snapshots" in capsys.readouterr().out

    s.upsert_athlete(Athlete(id="ana", name="Ana"))
    for resp in ("stable", "stable", "speed-dominant"):
        s.append_dossier_snapshot(DossierSnapshot(
            athlete_id="ana", responder=resp, current_vdot=50.0,
            demonstrated_opener_mpw=30.0, peak_mpw=50.0, anchor_age_days=70, anchor_stale=True,
        ))
    rc = main._cmd_dossier_log(_args(db=str(s.path), json=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert '"stable": 2' in out
    assert '"speed-dominant": 1' in out
    assert '"stale": 3' in out


def test_plan_log_groups_by_version(tmp_path: Path, capsys) -> None:
    s = _store(tmp_path)
    s.upsert_athlete(Athlete(id="ana", name="Ana"))
    s.save_plan_artifact("ana", build_plan(_inputs()), inputs_hash="h1")
    rc = main._cmd_plan_log(_args(db=str(s.path), json=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert f'"engine_version": "{ENGINE_VERSION}"' in out
    assert f'"club_policy_version": "{ClubPolicy().version}"' in out
