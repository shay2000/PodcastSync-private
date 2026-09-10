"""Unit tests for DatabaseManager behaviour that the HTTP suite cannot reach.

Covers the field allowlists on the dynamic-SQL update helpers and the
transactionality of the migration runner — guarantees that future refactors
must preserve.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from backend.database import DatabaseManager


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    manager = DatabaseManager(tmp_path / "podcastsync.db")
    manager.initialize()
    yield manager
    manager.close()


def _add_source(db: DatabaseManager) -> int:
    return db.add_source(
        name="S", source_type="channel", youtube_id="UCx", url="https://youtube.com/x"
    )


def _add_video(db: DatabaseManager, source_id: int) -> int:
    vid = db.add_video(source_id=source_id, video_id="v1", title="T")
    assert vid is not None
    return vid


# --- Dynamic-SQL field allowlists ----------------------------------------------


def test_update_source_rejects_unknown_fields(db):
    source_id = _add_source(db)
    with pytest.raises(ValueError, match="update_source: invalid field"):
        db.update_source(source_id, name="ok", evil="1; DROP TABLE sources")


def test_update_source_ignores_an_empty_update(db):
    source_id = _add_source(db)
    before = dict(db.get_source(source_id))
    db.update_source(source_id)
    assert dict(db.get_source(source_id)) == before


def test_update_source_accepts_every_allowlisted_field(db):
    source_id = _add_source(db)
    db.update_source(
        source_id,
        name="Renamed",
        enabled=False,
        max_backfill=10,
        custom_storage_path="/tmp/x",
        icon_url="https://example.invalid/i.png",
        max_keep_episodes=3,
    )
    row = db.get_source(source_id)
    assert row["name"] == "Renamed"
    assert row["enabled"] == 0
    assert row["max_backfill"] == 10
    assert row["custom_storage_path"] == "/tmp/x"
    assert row["icon_url"] == "https://example.invalid/i.png"
    assert row["max_keep_episodes"] == 3


def test_update_video_status_rejects_unknown_fields(db):
    source_id = _add_source(db)
    video_id = _add_video(db, source_id)
    with pytest.raises(ValueError, match="update_video_status: invalid field"):
        db.update_video_status(video_id, "completed", download_status="failed")


def test_update_video_status_accepts_every_allowlisted_field(db):
    source_id = _add_source(db)
    video_id = _add_video(db, source_id)
    db.update_video_status(
        video_id, "completed", file_path="/tmp/a.mp3", file_size=99, error_message=None
    )
    row = db.fetch_one("SELECT * FROM videos WHERE id = ?", (video_id,))
    assert row["download_status"] == "completed"
    assert row["file_path"] == "/tmp/a.mp3"
    assert row["file_size"] == 99
    assert row["error_message"] is None


# --- Migration runner transactionality -----------------------------------------


def test_failed_migration_is_rolled_back_completely(tmp_path, monkeypatch):
    """A script that fails mid-way must leave no trace of its earlier statements."""
    from backend import database as database_module

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    # v1 creates the schema; v2 does half its work then fails.
    (migrations / "001_init.sql").write_text(
        "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);\n"
        "CREATE TABLE t (id INTEGER PRIMARY KEY);\n"
    )
    (migrations / "002_bad.sql").write_text(
        "CREATE TABLE t2 (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO t2 VALUES (1);\n"
        "CREATE TABLE t2 (id INTEGER PRIMARY KEY);\n"  # duplicate -> error
    )
    monkeypatch.setattr(database_module, "MIGRATIONS_DIR", migrations)

    manager = DatabaseManager(tmp_path / "db.sqlite")
    with pytest.raises(sqlite3.OperationalError):
        manager.initialize()

    # Nothing from 002 survived: not its table, not its row, not the version bump.
    assert manager._get_schema_version() == 1
    assert manager.fetch_one("SELECT name FROM sqlite_master WHERE name = 't2'") is None
    manager.close()


def test_successful_migrations_apply_in_order_and_bump_version(tmp_path, monkeypatch):
    from backend import database as database_module

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_init.sql").write_text(
        "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);\n"
        "CREATE TABLE t (id INTEGER PRIMARY KEY);\n"
    )
    (migrations / "002_ok.sql").write_text("ALTER TABLE t ADD COLUMN note TEXT;\n")
    monkeypatch.setattr(database_module, "MIGRATIONS_DIR", migrations)

    manager = DatabaseManager(tmp_path / "db.sqlite")
    manager.initialize()
    assert manager._get_schema_version() == 2
    cols = {r["name"] for r in manager.fetch_all("PRAGMA table_info(t)")}
    assert "note" in cols
    manager.close()
