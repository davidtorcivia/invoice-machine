"""Recurring invoices API endpoints."""

from datetime import date
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from invoicely.database import get_session, RecurringSchedule
from invoicely.services import RecurringService

router = APIRouter(prefix="/api/recurring", tags=["recurring"])


class LineItemSchema(BaseModel):
    """Line item for recurring schedule."""

    description: str = Field(..., min_length=1, max_length=2000)
    quantity: int = Field(1, ge=1, le=10000)
    unit_type: str = Field("qty", pattern="^(qty|hours)$")
    unit_price: str


class RecurringScheduleSchema(BaseModel):
    """Recurring schedule response schema."""

    id: int
    client_id: int
    client_name: Optional[str] = None
    client_business: Optional[str] = None
    name: str
    frequency: str
    schedule_day: int
    currency_code: str
    payment_terms_days: int
    notes: Optional[str] = None
    line_items: Optional[List[dict]] = None
    tax_enabled: Optional[bool] = None
    tax_rate: Optional[str] = None
    tax_name: Optional[str] = None
    is_active: bool
    next_invoice_date: date
    last_invoice_id: Optional[int] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class RecurringScheduleCreate(BaseModel):
    """Create recurring schedule request."""

    client_id: int
    name: str = Field(..., min_length=1, max_length=255)
    frequency: str = Field(..., pattern="^(daily|weekly|monthly|quarterly|yearly)$")
    schedule_day: int = Field(1, ge=0, le=31)
    currency_code: str = Field("USD", max_length=3)
    payment_terms_days: int = Field(30, ge=0, le=365)
    notes: Optional[str] = Field(None, max_length=10000)
    line_items: Optional[List[LineItemSchema]] = None
    tax_enabled: Optional[bool] = None
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    tax_name: Optional[str] = Field(None, max_length=50)
    next_invoice_date: Optional[date] = None


class RecurringScheduleUpdate(BaseModel):
    """Update recurring schedule request."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    frequency: Optional[str] = Field(None, pattern="^(daily|weekly|monthly|quarterly|yearly)$")
    schedule_day: Optional[int] = Field(None, ge=0, le=31)
    currency_code: Optional[str] = Field(None, max_length=3)
    payment_terms_days: Optional[int] = Field(None, ge=0, le=365)
    notes: Optional[str] = Field(None, max_length=10000)
    line_items: Optional[List[LineItemSchema]] = None
    tax_enabled: Optional[bool] = None
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    tax_name: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
    next_invoice_date: Optional[date] = None


def _schedule_to_dict(schedule: RecurringSchedule) -> dict:
    """Convert schedule to response dict."""
    import json

    line_items = None
    if schedule.line_items:
        try:
            line_items = json.loads(schedule.line_items)
        except (json.JSONDecodeError, TypeError):
            line_items = None

    return {
        "id": schedule.id,
        "client_id": schedule.client_id,
        "client_name": schedule.client.name if schedule.client else None,
        "client_business": schedule.client.business_name if schedule.client else None,
        "name": schedule.name,
        "frequency": schedule.frequency,
        "schedule_day": schedule.schedule_day,
        "currency_code": schedule.currency_code,
        "payment_terms_days": schedule.payment_terms_days,
        "notes": schedule.notes,
        "line_items": line_items,
        "tax_enabled": bool(schedule.tax_enabled) if schedule.tax_enabled is not None else None,
        "tax_rate": str(schedule.tax_rate) if schedule.tax_rate is not None else None,
        "tax_name": schedule.tax_name,
        "is_active": bool(schedule.is_active),
        "next_invoice_date": schedule.next_invoice_date.isoformat(),
        "last_invoice_id": schedule.last_invoice_id,
        "created_at": schedule.created_at.isoformat(),
        "updated_at": schedule.updated_at.isoformat(),
    }


@router.get("")
async def list_schedules(
    client_id: Optional[int] = None,
    active_only: bool = True,
    session: AsyncSession = Depends(get_session),
) -> List[dict]:
    """List recurring schedules."""
    schedules = await RecurringService.list_schedules(
        session, client_id=client_id, active_only=active_only
    )
    return [_schedule_to_dict(s) for s in schedules]


@router.post("", status_code=201)
async def create_schedule(
    data: RecurringScheduleCreate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a new recurring schedule."""
    try:
        # Convert line items to list of dicts
        line_items = None
        if data.line_items:
            line_items = [item.model_dump() for item in data.line_items]

        schedule = await RecurringService.create_schedule(
            session,
            client_id=data.client_id,
            name=data.name,
            frequency=data.frequency,
            schedule_day=data.schedule_day,
            currency_code=data.currency_code,
            payment_terms_days=data.payment_terms_days,
            notes=data.notes,
            line_items=line_items,
            tax_enabled=int(data.tax_enabled) if data.tax_enabled is not None else None,
            tax_rate=data.tax_rate,
            tax_name=data.tax_name,
            next_invoice_date=data.next_invoice_date,
        )
        return _schedule_to_dict(schedule)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{schedule_id}")
async def get_schedule(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get a recurring schedule by ID."""
    schedule = await RecurringService.get_schedule(session, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _schedule_to_dict(schedule)


@router.put("/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    data: RecurringScheduleUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update a recurring schedule."""
    # Build update kwargs
    update_data = data.model_dump(exclude_unset=True)

    # Convert line items to list of dicts
    if "line_items" in update_data and update_data["line_items"] is not None:
        update_data["line_items"] = [
            item if isinstance(item, dict) else item.model_dump()
            for item in update_data["line_items"]
        ]

    # Convert tax_enabled to int
    if "tax_enabled" in update_data and update_data["tax_enabled"] is not None:
        update_data["tax_enabled"] = int(update_data["tax_enabled"])

    # Convert is_active to int
    if "is_active" in update_data and update_data["is_active"] is not None:
        update_data["is_active"] = int(update_data["is_active"])

    schedule = await RecurringService.update_schedule(session, schedule_id, **update_data)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _schedule_to_dict(schedule)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a recurring schedule."""
    deleted = await RecurringService.delete_schedule(session, schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Schedule not found")


@router.post("/{schedule_id}/pause")
async def pause_schedule(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Pause a recurring schedule."""
    success = await RecurringService.pause_schedule(session, schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule = await RecurringService.get_schedule(session, schedule_id)
    return _schedule_to_dict(schedule)


@router.post("/{schedule_id}/resume")
async def resume_schedule(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Resume a paused recurring schedule."""
    success = await RecurringService.resume_schedule(session, schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule = await RecurringService.get_schedule(session, schedule_id)
    return _schedule_to_dict(schedule)


@router.post("/{schedule_id}/trigger")
async def trigger_schedule(
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Manually trigger a recurring schedule to create an invoice now."""
    try:
        result = await RecurringService.trigger_schedule(session, schedule_id)
        if not result.get("success"):
            error = result.get("error", "Failed to trigger schedule")
            if "not found" in error.lower():
                raise HTTPException(status_code=404, detail="Schedule not found")
            raise HTTPException(status_code=400, detail=error)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
