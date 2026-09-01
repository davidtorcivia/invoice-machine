"""Tests for the startup schema bootstrap in runtime_schema.py."""

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from invoice_machine import runtime_schema


def _make_db(path, *, users=True, alembic_version=None):
    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()
    if users:
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(100))")
    if alembic_version is not None:
        cursor.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        cursor.execute("INSERT INTO alembic_version VALUES (?)", (alembic_version,))
    conn.commit()
    conn.close()


def test_inspect_reports_a_database_without_alembic(tmp_path):
    db_path = tmp_path / "invoice_machine.db"
    _make_db(db_path)

    assert runtime_schema._inspect_existing_db(db_path) == (False, None, True)


def test_inspect_remaps_a_legacy_revision_id_in_place(tmp_path):
    db_path = tmp_path / "invoice_machine.db"
    _make_db(db_path, alembic_version="008_add_line_items_fts")

    has_alembic, version, has_users = runtime_schema._inspect_existing_db(db_path)

    assert (has_alembic, version, has_users) == (True, "008_line_items_fts", True)
    conn = sqlite3.connect(str(db_path))
    assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
        "008_line_items_fts"
    )
    conn.close()


def test_pre_alembic_database_is_refused_with_manual_instructions(tmp_path, monkeypatch):
    db_path = tmp_path / "invoice_machine.db"
    _make_db(db_path)
    monkeypatch.setattr(runtime_schema, "settings", SimpleNamespace(data_dir=tmp_path))

    with pytest.raises(RuntimeError) as excinfo:
        runtime_schema.run_alembic_migrations()

    message = str(excinfo.value)
    assert "alembic stamp 001_initial" in message
    assert "alembic upgrade head" in message


def test_database_under_alembic_is_upgraded_to_head(tmp_path, monkeypatch):
    db_path = tmp_path / "invoice_machine.db"
    _make_db(db_path, alembic_version="001_initial")
    monkeypatch.setattr(runtime_schema, "settings", SimpleNamespace(data_dir=tmp_path))
    upgrade = MagicMock()
    monkeypatch.setattr("alembic.command.upgrade", upgrade)

    runtime_schema.run_alembic_migrations()

    assert upgrade.call_args[0][1] == "head"


def test_missing_database_file_is_upgraded_from_scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_schema, "settings", SimpleNamespace(data_dir=tmp_path))
    upgrade = MagicMock()
    monkeypatch.setattr("alembic.command.upgrade", upgrade)

    runtime_schema.run_alembic_migrations()

    assert upgrade.call_args[0][1] == "head"


@pytest.mark.asyncio
async def test_ensure_database_schema_can_skip_migrations(monkeypatch):
    prepared = MagicMock()
    init_db = MagicMock()

    async def fake_init_db():
        init_db()

    monkeypatch.setattr("invoice_machine.config.prepare_runtime", prepared)
    monkeypatch.setattr(runtime_schema, "init_db", fake_init_db)
    monkeypatch.setattr(
        runtime_schema,
        "run_alembic_migrations",
        MagicMock(side_effect=AssertionError("must not migrate")),
    )

    await runtime_schema.ensure_database_schema(apply_migrations=False)

    assert prepared.called and init_db.called
