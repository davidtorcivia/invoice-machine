"""Shared database schema/bootstrap helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from invoice_machine.config import get_settings
from invoice_machine.database import init_db

settings = get_settings()


def sqlite_path_from_url(database_url: str) -> Path | None:
    """Extract SQLite file path from a SQLAlchemy URL, if applicable."""
    if database_url.startswith("sqlite+aiosqlite:///"):
        return Path(database_url.replace("sqlite+aiosqlite:///", "", 1))
    if database_url.startswith("sqlite:///"):
        return Path(database_url.replace("sqlite:///", "", 1))
    return None


def run_alembic_migrations() -> None:
    """Run Alembic migrations to upgrade database schema."""
    from alembic import command
    from alembic.config import Config

    old_to_new_revisions = {
        "007_add_default_currency": "007_default_currency",
        "008_add_line_items_fts": "008_line_items_fts",
        "009_add_sessions": "009_recurring_enhancements",
    }

    project_root = Path(__file__).parent.parent
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    db_path = settings.data_dir / "invoice_machine.db"

    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            )
            has_alembic_table = cursor.fetchone() is not None

            has_valid_version = False
            current_version = None
            if has_alembic_table:
                cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
                row = cursor.fetchone()
                if row:
                    has_valid_version = True
                    current_version = row[0]

            if current_version and current_version in old_to_new_revisions:
                new_version = old_to_new_revisions[current_version]
                print(f"Updating alembic version from {current_version} to {new_version}...")
                cursor.execute("UPDATE alembic_version SET version_num = ?", (new_version,))
                conn.commit()
                print("Alembic version updated successfully")

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            )
            has_users = cursor.fetchone() is not None
            conn.close()

            if has_users and not has_valid_version:
                print("Existing database detected without valid alembic version...")
                print("Running fallback migration to ensure schema is complete...")
                from invoice_machine.migrations.add_new_fields import migrate

                migrate(settings.data_dir / "invoice_machine.db")
        except Exception as exc:
            print(f"Database check failed: {exc}")

    try:
        command.upgrade(alembic_cfg, "head")
        print("Alembic migrations completed successfully")
    except Exception as exc:
        print(f"Alembic migration failed: {exc}")
        from invoice_machine.migrations.add_new_fields import migrate

        migrate(settings.data_dir / "invoice_machine.db")
        try:
            command.stamp(alembic_cfg, "head")
            print("Database stamped at head after fallback migration")
        except Exception as stamp_error:
            print(f"Warning: Could not stamp database: {stamp_error}")


async def ensure_database_schema(*, apply_migrations: bool = True) -> None:
    """Bring the database schema to a usable state for app or MCP startup."""
    if apply_migrations:
        run_alembic_migrations()
    await init_db()
