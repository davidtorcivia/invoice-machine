"""Guard against schema drift between SQLAlchemy models and Alembic migrations.

The app runs `alembic upgrade head` on startup against a real file database, but
the rest of the test suite builds the schema with `Base.metadata.create_all`. So
a column added to a model without a matching migration (or vice versa) would not
be caught by any other test. This test runs the real migrations on a throwaway
database and asserts every model table/column exists in the result.
"""

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from invoice_machine.database import Base

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_UPGRADE_SNIPPET = (
    "from alembic.config import Config; from alembic import command; "
    "command.upgrade(Config('alembic.ini'), 'head')"
)


def test_alembic_head_has_all_model_columns():
    with tempfile.TemporaryDirectory() as tmp:
        db_file = Path(tmp) / "drift.db"
        env = dict(os.environ)
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
        env["ENVIRONMENT"] = "development"

        result = subprocess.run(
            [sys.executable, "-c", _UPGRADE_SNIPPET],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"`alembic upgrade head` failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
        assert db_file.exists(), "migrations did not create the database file"

        conn = sqlite3.connect(str(db_file))
        try:
            cur = conn.cursor()
            db_tables = {
                row[0]
                for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            missing: list[str] = []
            for table in Base.metadata.tables.values():
                if table.name not in db_tables:
                    missing.append(f"missing table: {table.name}")
                    continue
                cols = {row[1] for row in cur.execute(f"PRAGMA table_info('{table.name}')")}
                for column in table.columns:
                    if column.name not in cols:
                        missing.append(f"missing column: {table.name}.{column.name}")
        finally:
            conn.close()

        assert not missing, "Schema drift between models and Alembic head:\n" + "\n".join(missing)


def test_alembic_head_keeps_fts_triggers():
    """The line-item FTS sync triggers must survive `alembic upgrade head`.

    Migration 013 rebuilds invoice_items via batch_alter, which silently drops the
    triggers created in 008; 013 must recreate them or new line items stop being
    indexed for search.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_file = Path(tmp) / "fts.db"
        env = dict(os.environ)
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file}"
        env["ENVIRONMENT"] = "development"

        result = subprocess.run(
            [sys.executable, "-c", _UPGRADE_SNIPPET],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"`alembic upgrade head` failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

        conn = sqlite3.connect(str(db_file))
        try:
            triggers = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' "
                    "AND name LIKE 'invoice_items_fts_%'"
                )
            }
        finally:
            conn.close()

        assert {
            "invoice_items_fts_insert",
            "invoice_items_fts_delete",
            "invoice_items_fts_update",
        } <= triggers, f"FTS triggers missing after migration: {triggers}"
