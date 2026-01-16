"""Trash/Restore API endpoints."""

from datetime import datetime
from typing import List, Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from invoicely.database import Client, Invoice, get_session
from invoicely.services import ClientService, InvoiceService

router = APIRouter(prefix="/api/trash", tags=["trash"])


class TrashedItemSchema(BaseModel):
    """Schema for a trashed item."""

    type: Literal["client", "invoice"]
    id: int
    name: str
    deleted_at: datetime
    days_until_purge: int


@router.get("", response_model=List[TrashedItemSchema])
async def list_trash(
    session: AsyncSession = Depends(get_session),
) -> List[TrashedItemSchema]:
    """List all trashed items."""
    from datetime import timedelta
    from invoicely.config import get_settings

    settings = get_settings()
    purge_threshold = datetime.utcnow() - timedelta(days=settings.trash_retention_days)

    items = []

    # Get trashed clients
    from sqlalchemy import select

    client_result = await session.execute(
        select(Client).where(Client.deleted_at.is_not(None))
    )
    for client in client_result.scalars():
        days_left = settings.trash_retention_days - int(
            (datetime.utcnow() - client.deleted_at).total_seconds() / 86400
        )
        items.append(
            TrashedItemSchema(
                type="client",
                id=client.id,
                name=client.display_name,
                deleted_at=client.deleted_at,
                days_until_purge=days_left,
            )
        )

    # Get trashed invoices
    invoice_result = await session.execute(
        select(Invoice).where(Invoice.deleted_at.is_not(None))
    )
    for invoice in invoice_result.scalars():
        days_left = settings.trash_retention_days - int(
            (datetime.utcnow() - invoice.deleted_at).total_seconds() / 86400
        )
        items.append(
            TrashedItemSchema(
                type="invoice",
                id=invoice.id,
                name=invoice.invoice_number,
                deleted_at=invoice.deleted_at,
                days_until_purge=days_left,
            )
        )

    # Sort by deletion date, newest first
    items.sort(key=lambda x: x.deleted_at, reverse=True)
    return items


@router.post("/empty", status_code=204)
async def empty_trash(session: AsyncSession = Depends(get_session)):
    """Permanently delete all trashed items immediately."""
    from sqlalchemy import delete

    # Delete all trashed clients
    await session.execute(
        delete(Client).where(Client.deleted_at.is_not(None))
    )

    # Delete all trashed invoices (cascade to items)
    await session.execute(
        delete(Invoice).where(Invoice.deleted_at.is_not(None))
    )

    await session.commit()


@router.post("/restore/{item_type}/{item_id}", status_code=204)
async def restore_trashed_item(
    item_type: Literal["client", "invoice"],
    item_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Restore a trashed item."""
    if item_type == "client":
        success = await ClientService.restore_client(session, item_id)
    else:
        success = await InvoiceService.restore_invoice(session, item_id)

    if not success:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Item not found or not deleted")
