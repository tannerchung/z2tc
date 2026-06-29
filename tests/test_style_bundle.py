"""Folding the club style bundle into the store's config kv: set/get roundtrip and the publish-time
resolver (`main._load_style_bundle`) preferring an explicit file but falling back to the store."""

from __future__ import annotations

import json
from pathlib import Path

import main
from store.db import SCHEMA_VERSION, STYLE_BUNDLE_KEY, Store


def _store(tmp_path: Path) -> Store:
    return Store(db_path=tmp_path / "cfg.db", project_root=tmp_path)


def test_config_roundtrip_and_schema_version(tmp_path: Path) -> None:
    db = _store(tmp_path)
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert db.get_config("missing") is None

    db.set_config(STYLE_BUNDLE_KEY, {"spreadsheet_id": "SS", "style_spec": {"notes": "v1"}})
    assert db.get_config(STYLE_BUNDLE_KEY)["spreadsheet_id"] == "SS"
    # Upsert replaces the value under the same key.
    db.set_config(STYLE_BUNDLE_KEY, {"spreadsheet_id": "SS2", "style_spec": {}})
    assert db.get_config(STYLE_BUNDLE_KEY)["spreadsheet_id"] == "SS2"


def test_load_style_bundle_from_store_when_no_file(tmp_path: Path) -> None:
    db = _store(tmp_path)
    db.set_config(STYLE_BUNDLE_KEY, {"spreadsheet_id": "FROM_DB", "style_spec": {"notes": "db"}})

    resolved = main._load_style_bundle(db, str(tmp_path / "does_not_exist.json"))
    assert resolved is not None
    spec, ss_id = resolved
    assert ss_id == "FROM_DB" and spec.notes == "db"


def test_explicit_file_overrides_store(tmp_path: Path) -> None:
    db = _store(tmp_path)
    db.set_config(STYLE_BUNDLE_KEY, {"spreadsheet_id": "FROM_DB", "style_spec": {}})

    f = tmp_path / "bundle.json"
    f.write_text(json.dumps({"spreadsheet_id": "FROM_FILE", "style_spec": {"notes": "file"}}), encoding="utf-8")
    resolved = main._load_style_bundle(db, str(f))
    assert resolved is not None
    spec, ss_id = resolved
    assert ss_id == "FROM_FILE" and spec.notes == "file"


def test_load_style_bundle_none_when_neither(tmp_path: Path) -> None:
    db = _store(tmp_path)
    assert main._load_style_bundle(db, str(tmp_path / "nope.json")) is None
    assert main._load_style_bundle(db, None) is None
