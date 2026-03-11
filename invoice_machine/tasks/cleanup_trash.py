"""Scheduled task: Cleanup old trashed items.

Run via cron or manually:
    docker exec invoice-machine python -m invoice_machine.tasks.cleanup_trash
"""

import asyncio
from datetime import timedelta

from invoice_machine.config import get_settings
from invoice_machine.database import async_session_maker
from invoice_machine.services import purge_trashed_records
from invoice_machine.utils import utc_now


async def cleanup_trash():
    """Permanently delete items older than retention period."""
    settings = get_settings()
    purge_threshold = timedelta(days=settings.trash_retention_days)

    async with async_session_maker() as session:
        cutoff = utc_now() - purge_threshold

        result = await purge_trashed_records(session, deleted_before=cutoff)
        await session.commit()

        print(
            "Cleanup complete: "
            f"{result['clients_deleted']} clients, {result['invoices_deleted']} invoices purged"
        )


if __name__ == "__main__":
    asyncio.run(cleanup_trash())
