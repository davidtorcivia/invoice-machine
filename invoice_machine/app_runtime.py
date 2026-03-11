"""Application startup, migration, and background task orchestration."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI

from invoice_machine.config import get_settings
from invoice_machine.database import close_db, init_db
from invoice_machine.utils import utc_now

logger = logging.getLogger(__name__)
settings = get_settings()


def _startup_notice(message: str) -> None:
    """Emit a startup/shutdown message consistently."""
    print(message, flush=True)


def _seconds_until_hour(target_hour_utc: int) -> float:
    """Return seconds until the next UTC clock hour."""
    now = utc_now()
    target = now.replace(hour=target_hour_utc, minute=0, second=0, microsecond=0)
    if now.hour >= target_hour_utc:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _run_hourly_task(app: FastAPI, job) -> None:
    """Run a task once per hour, skipping restore windows."""
    while True:
        await asyncio.sleep(3600)
        if app.state.restore_in_progress:
            continue
        await job()


async def _run_daily_task(app: FastAPI, hour_utc: int, name: str, job) -> None:
    """Run a task daily at a given UTC hour, skipping restore windows."""
    while True:
        await asyncio.sleep(_seconds_until_hour(hour_utc))
        try:
            if app.state.restore_in_progress:
                continue
            await job()
        except Exception as exc:
            logger.error("%s failed: %s", name, exc, exc_info=True)


async def _session_cleanup_job() -> None:
    """Clean up expired sessions."""
    from invoice_machine.api.auth import run_session_cleanup

    await run_session_cleanup()


async def _scheduled_backup_job() -> None:
    """Create scheduled backups and prune old ones."""
    import json

    from invoice_machine.database import BusinessProfile, async_session_maker
    from invoice_machine.services import BackupService

    async with async_session_maker() as session:
        profile = await BusinessProfile.get(session)
        if not profile or not profile.backup_enabled:
            return

        s3_config = None
        if profile.backup_s3_enabled and profile.backup_s3_config:
            try:
                s3_config = json.loads(profile.backup_s3_config)
                s3_config["enabled"] = True
            except json.JSONDecodeError:
                s3_config = None

        backup_service = BackupService(
            retention_days=profile.backup_retention_days or 30,
            s3_config=s3_config,
        )
        backup_service.create_backup(compress=True)
        backup_service.cleanup_old_backups()
        logger.info("Scheduled backup completed successfully")


async def _trash_cleanup_job() -> None:
    """Purge expired trash items."""
    from invoice_machine.tasks.cleanup_trash import cleanup_trash

    await cleanup_trash()


async def _overdue_check_job() -> None:
    """Mark due invoices as overdue."""
    from invoice_machine.database import async_session_maker
    from invoice_machine.services import InvoiceService

    async with async_session_maker() as session:
        count = await InvoiceService.update_overdue_invoices(session)
        if count > 0:
            logger.info("Marked %s invoices as overdue", count)


async def _recurring_invoice_job() -> None:
    """Process due recurring schedules."""
    from invoice_machine.database import async_session_maker
    from invoice_machine.services import RecurringService

    async with async_session_maker() as session:
        results = await RecurringService.process_due_schedules(session)
        if results:
            success_count = sum(1 for result in results if result.get("success"))
            logger.info(
                "Processed %s recurring schedules, %s invoices created",
                len(results),
                success_count,
            )


def run_alembic_migrations() -> None:
    """Run Alembic migrations to upgrade database schema."""
    import sqlite3

    from alembic import command
    from alembic.config import Config

    OLD_TO_NEW_REVISIONS = {
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

            if current_version and current_version in OLD_TO_NEW_REVISIONS:
                new_version = OLD_TO_NEW_REVISIONS[current_version]
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


async def _rebuild_search_indexes() -> None:
    """Rebuild FTS indexes on startup when required."""
    from invoice_machine.database import async_session_maker
    from invoice_machine.services import SearchService

    async with async_session_maker() as session:
        reindex_result = await SearchService.reindex_fts(session)
        if reindex_result.get("skipped"):
            _startup_notice(
                f"FTS rebuild skipped: {reindex_result.get('reason', 'no data')}"
            )
        elif reindex_result.get("error"):
            _startup_notice(f"FTS rebuild error: {reindex_result.get('error')}")
        elif reindex_result.get("rebuilt"):
            _startup_notice(
                "FTS rebuild complete: "
                f"{reindex_result.get('invoices_indexed', 0)} invoices, "
                f"{reindex_result.get('clients_indexed', 0)} clients, "
                f"{reindex_result.get('line_items_indexed', 0)} line items indexed"
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager."""
    _startup_notice("Starting Invoice Machine...")
    _startup_notice("Running database migrations...")
    run_alembic_migrations()
    _startup_notice("Migrations complete.")

    _startup_notice("Initializing database...")
    await init_db()
    _startup_notice("Database initialized.")

    _startup_notice("Rebuilding FTS search indexes...")
    try:
        await _rebuild_search_indexes()
    except Exception as exc:
        _startup_notice(f"FTS rebuild failed (non-fatal): {exc}")

    _startup_notice("Starting background tasks...")
    tasks = [
        asyncio.create_task(_run_hourly_task(app, _session_cleanup_job)),
        asyncio.create_task(_run_daily_task(app, 0, "Scheduled backup task", _scheduled_backup_job)),
        asyncio.create_task(_run_daily_task(app, 3, "Trash cleanup task", _trash_cleanup_job)),
        asyncio.create_task(_run_daily_task(app, 1, "Overdue check task", _overdue_check_job)),
        asyncio.create_task(_run_daily_task(app, 2, "Recurring invoice task", _recurring_invoice_job)),
    ]
    _startup_notice("Background tasks started.")
    _startup_notice("Invoice Machine ready! Listening on port 8080")

    yield

    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await close_db()
