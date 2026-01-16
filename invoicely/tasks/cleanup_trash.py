"""Scheduled task: Cleanup old trashed items.

Run via cron or manually:
    docker exec invoicely python -m invoicely.tasks.cleanup_trash
"""

import asyncio
from datetime import timedelta

from sqlalchemy import delete, and_

from invoicely.database import async_session_maker, Client, Invoice
from invoicely.config import get_settings


async def cleanup_trash():
    """Permanently delete items older than retention period."""
    settings = get_settings()
    purge_threshold = timedelta(days=settings.trash_retention_days)

    async with async_session_maker() as session:
        from datetime import datetime
        cutoff = datetime.utcnow() - purge_threshold

        # Count items to be deleted
        from sqlalchemy import select, func

        client_count_result = await session.execute(
            select(func.count(Client.id)).where(
                and_(
                    Client.deleted_at.is_not(None),
                    Client.deleted_at < cutoff,
                )
            )
        )
        invoice_count_result = await session.execute(
            select(func.count(Invoice.id)).where(
                and_(
                    Invoice.deleted_at.is_not(None),
                    Invoice.deleted_at < cutoff,
                )
            )
        )

        clients_deleted = client_count_result.scalar() or 0
        invoices_deleted = invoice_count_result.scalar() or 0

        # Delete
        await session.execute(
            delete(Client).where(
                and_(
                    Client.deleted_at.is_not(None),
                    Client.deleted_at < cutoff,
                )
            )
        )
        await session.execute(
            delete(Invoice).where(
                and_(
                    Invoice.deleted_at.is_not(None),
                    Invoice.deleted_at < cutoff,
                )
            )
        )

        await session.commit()

        print(f"Cleanup complete: {clients_deleted} clients, {invoices_deleted} invoices purged")


if __name__ == "__main__":
    asyncio.run(cleanup_trash())
