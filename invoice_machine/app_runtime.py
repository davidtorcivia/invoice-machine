"""Application startup, migration, and background task orchestration."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import FastAPI

from invoice_machine.config import get_settings
from invoice_machine.database import close_db
from invoice_machine.runtime_schema import ensure_database_schema
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
    await ensure_database_schema(apply_migrations=True)
    _startup_notice("Migrations complete.")
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
