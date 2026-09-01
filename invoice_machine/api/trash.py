"""Trash/Restore API endpoints."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import Client, Invoice, get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.services import ClientService, InvoiceService, purge_trashed_records
from invoice_machine.utils import ensure_utc, utc_now

router = APIRouter(prefix="/api/trash", tags=["trash"])


class TrashedItemSchema(BaseModel):
    """Schema for a trashed item."""

    type: Literal["client", "invoice"]
    id: int
    name: str
    deleted_at: datetime
    days_until_purge: int


@router.get("", response_model=list[TrashedItemSchema])
@limiter.limit("60/minute")
async def list_trash(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> list[TrashedItemSchema]:
    """List all trashed items."""
    from invoice_machine.config import get_settings

    settings = get_settings()
    now = utc_now()

    items = []

    # Column-only selects: loading whole Invoice entities here would drag in the
    # selectin-loaded line items and client for every trashed row just to render
    # a name and a date.
    from sqlalchemy import select

    client_rows = await session.execute(
        select(Client.id, Client.name, Client.business_name, Client.deleted_at).where(
            Client.deleted_at.is_not(None)
        )
    )
    for row in client_rows:
        deleted_at = ensure_utc(row.deleted_at)
        if not deleted_at:
            continue
        days_left = settings.trash_retention_days - int((now - deleted_at).total_seconds() / 86400)
        items.append(
            TrashedItemSchema(
                type="client",
                id=row.id,
                name=row.business_name or row.name or "Unknown Client",
                deleted_at=deleted_at,
                days_until_purge=days_left,
            )
        )

    invoice_rows = await session.execute(
        select(Invoice.id, Invoice.invoice_number, Invoice.deleted_at).where(
            Invoice.deleted_at.is_not(None)
        )
    )
    for row in invoice_rows:
        deleted_at = ensure_utc(row.deleted_at)
        if not deleted_at:
            continue
        days_left = settings.trash_retention_days - int((now - deleted_at).total_seconds() / 86400)
        items.append(
            TrashedItemSchema(
                type="invoice",
                id=row.id,
                name=row.invoice_number,
                deleted_at=deleted_at,
                days_until_purge=days_left,
            )
        )

    items.sort(key=lambda x: x.deleted_at, reverse=True)
    return items


@router.post("/empty", status_code=204)
@limiter.limit("5/hour")
async def empty_trash(request: Request, session: AsyncSession = Depends(get_session)):
    """Permanently delete all trashed items immediately."""
    await purge_trashed_records(session)
    await session.commit()


@router.post("/restore/{item_type}/{item_id}", status_code=204)
@limiter.limit("30/hour")
async def restore_trashed_item(
    request: Request,
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
