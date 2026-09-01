"""Shared database schema/bootstrap helpers."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from invoice_machine.config import get_settings
from invoice_machine.database import init_db

logger = logging.getLogger(__name__)
settings = get_settings()

# Historical revision-id renames, so databases stamped under an old id can be
# remapped to the current id before upgrading.
_OLD_TO_NEW_REVISIONS = {
    "007_add_default_currency": "007_default_currency",
    "008_add_line_items_fts": "008_line_items_fts",
    "009_add_sessions": "009_recurring_enhancements",
}


def _inspect_existing_db(db_path: Path) -> tuple[bool, str | None, bool]:
    """Return (has_alembic_version, current_version, has_users) for an existing DB."""
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        )
        has_alembic = cursor.fetchone() is not None

        current_version = None
        if has_alembic:
            cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
            row = cursor.fetchone()
            current_version = row[0] if row else None

            # Remap any legacy revision id in place before upgrading.
            if current_version in _OLD_TO_NEW_REVISIONS:
                new_version = _OLD_TO_NEW_REVISIONS[current_version]
                logger.info("Remapping alembic version %s -> %s", current_version, new_version)
                cursor.execute("UPDATE alembic_version SET version_num = ?", (new_version,))
                conn.commit()
                current_version = new_version

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        has_users = cursor.fetchone() is not None
        return has_alembic, current_version, has_users
    finally:
        conn.close()


def run_alembic_migrations() -> None:
    """Upgrade the database schema to Alembic head.

    A pre-Alembic database (app tables but no alembic_version) is refused rather
    than guessed at: nothing here can tell which of the 001-021 revisions its
    schema already reflects, and stamping the wrong one loses tables silently.
    Any other database is upgraded and a failure propagates — head is never
    stamped over a partial migration.
    """
    from alembic import command
    from alembic.config import Config

    project_root = Path(__file__).parent.parent
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    db_path = settings.data_dir / "invoice_machine.db"

    if db_path.exists():
        has_alembic, _current_version, has_users = _inspect_existing_db(db_path)

        if has_users and not has_alembic:
            raise RuntimeError(
                f"The database at {db_path} predates Alembic (it has application tables "
                "but no alembic_version table) and cannot be upgraded automatically. "
                "Back it up, then migrate it by hand: `alembic stamp 001_initial` "
                "followed by `alembic upgrade head`."
            )

    # Fresh database or one already under Alembic control: upgrade, fail loudly.
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations completed successfully")


async def ensure_database_schema(*, apply_migrations: bool = True) -> None:
    """Bring the database schema to a usable state for app or MCP startup."""
    # One-time filesystem bootstrap (create data/pdf/logo dirs, legacy rename)
    # before anything touches the database file.
    from invoice_machine.config import prepare_runtime

    prepare_runtime()
    if apply_migrations:
        run_alembic_migrations()
    await init_db()
