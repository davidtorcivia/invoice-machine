"""Trash/Restore API endpoints."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.service.clients import ClientService
from invoice_machine.service.common import list_trashed, purge_trashed_records
from invoice_machine.service.invoices import InvoiceService

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
    return [TrashedItemSchema.model_validate(item) for item in await list_trashed(session)]


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
