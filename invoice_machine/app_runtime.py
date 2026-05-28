"""Application startup, migration, and background task orchestration."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI

from invoice_machine.config import get_settings
from invoice_machine.database import close_db
from invoice_machine.runtime_schema import ensure_database_schema
from invoice_machine.utils import utc_now

logger = logging.getLogger(__name__)
settings = get_settings()

# How long to wait between rechecks while a restore is in progress.
_RESTORE_WAIT_SECONDS = 60


def _seconds_until_hour(target_hour_utc: int) -> float:
    """Return seconds until the next occurrence of the given UTC clock hour."""
    now = utc_now()
    target = now.replace(hour=target_hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _wait_out_restore(app: FastAPI) -> None:
    """Block while a backup restore is in progress (recheck periodically)."""
    while getattr(app.state, "restore_in_progress", False):
        await asyncio.sleep(_RESTORE_WAIT_SECONDS)


async def _run_hourly_task(app: FastAPI, name: str, job) -> None:
    """Run a task once per hour. A failure is logged but never kills the loop."""
    while True:
        await asyncio.sleep(3600)
        await _wait_out_restore(app)
        try:
            await job()
        except Exception as exc:
            logger.error("%s failed: %s", name, exc, exc_info=True)


async def _run_daily_task(app: FastAPI, hour_utc: int, name: str, job) -> None:
    """Run a task daily at a given UTC hour. Waits out restores instead of
    skipping a whole day, and logs (does not propagate) failures."""
    while True:
        await asyncio.sleep(_seconds_until_hour(hour_utc))
        await _wait_out_restore(app)
        try:
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
            logger.info("FTS rebuild skipped: %s", reindex_result.get("reason", "no data"))
        elif reindex_result.get("error"):
            logger.warning("FTS rebuild error: %s", reindex_result.get("error"))
        elif reindex_result.get("rebuilt"):
            logger.info(
                "FTS rebuild complete: %s invoices, %s clients, %s line items indexed",
                reindex_result.get("invoices_indexed", 0),
                reindex_result.get("clients_indexed", 0),
                reindex_result.get("line_items_indexed", 0),
            )


def _acquire_scheduler_lock():
    """Acquire a single-instance lock so only one process runs the scheduler.

    Returns the open file handle (which must be kept alive to hold the lock) or
    None if another process already holds it. Best-effort; on platforms without
    fcntl the scheduler simply runs.
    """
    try:
        import fcntl
    except ImportError:
        return object()  # No advisory locking available; run unconditionally.

    lock_path = settings.data_dir / "scheduler.lock"
    handle = open(lock_path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except OSError:
        handle.close()
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager."""
    logger.info("Starting Invoice Machine...")
    logger.info("Running database migrations...")
    await ensure_database_schema(apply_migrations=True)
    logger.info("Database initialized.")

    logger.info("Rebuilding FTS search indexes...")
    try:
        await _rebuild_search_indexes()
    except Exception as exc:
        logger.warning("FTS rebuild failed (non-fatal): %s", exc, exc_info=True)

    # Run time-sensitive jobs once at startup so a restart doesn't skip a day.
    # Both are idempotent (recurring catches up missed periods exactly once).
    for name, job in (("Overdue check", _overdue_check_job), ("Recurring invoices", _recurring_invoice_job)):
        try:
            await job()
        except Exception as exc:
            logger.warning("%s at startup failed (non-fatal): %s", name, exc, exc_info=True)

    tasks: list[asyncio.Task] = []
    scheduler_lock = _acquire_scheduler_lock()
    if scheduler_lock is None:
        logger.warning(
            "Another process holds the scheduler lock; background tasks will not "
            "run in this worker (expected with multiple workers)."
        )
    else:
        logger.info("Starting background tasks...")
        tasks = [
            asyncio.create_task(_run_hourly_task(app, "Session cleanup", _session_cleanup_job)),
            asyncio.create_task(_run_daily_task(app, 0, "Scheduled backup task", _scheduled_backup_job)),
            asyncio.create_task(_run_daily_task(app, 3, "Trash cleanup task", _trash_cleanup_job)),
            asyncio.create_task(_run_daily_task(app, 1, "Overdue check task", _overdue_check_job)),
            asyncio.create_task(_run_daily_task(app, 2, "Recurring invoice task", _recurring_invoice_job)),
        ]
    logger.info("Invoice Machine ready! Listening on port %s", settings.port)

    yield

    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    if scheduler_lock is not None and hasattr(scheduler_lock, "close"):
        scheduler_lock.close()
    await close_db()
