"""Recurring invoices API endpoints."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from invoice_machine.api.schemas import LineItemCreate
from invoice_machine.database import RecurringSchedule, get_session
from invoice_machine.presenters import serialize_recurring_schedule
from invoice_machine.rate_limit import limiter
from invoice_machine.services import RecurringService

router = APIRouter(prefix="/api/recurring", tags=["recurring"])


def _validate_schedule_day_for_frequency(
    frequency: str | None,
    schedule_day: int | None,
) -> None:
    """Validate schedule_day against the selected frequency when possible."""
    if frequency is None or schedule_day is None:
        return

    if frequency == "weekly" and not (0 <= schedule_day <= 6):
        raise ValueError("For weekly frequency, schedule_day must be 0-6 (Monday-Sunday)")

    if frequency in {"monthly", "quarterly", "yearly"} and not (1 <= schedule_day <= 31):
        raise ValueError("For monthly/quarterly/yearly frequency, schedule_day must be 1-31")


class RecurringScheduleCreate(BaseModel):
    """Create recurring schedule request."""

    client_id: int
    name: str = Field(..., min_length=1, max_length=255)
    frequency: str = Field(..., pattern="^(daily|weekly|monthly|quarterly|yearly)$")
    schedule_day: int = Field(1, ge=0, le=31)
    # Which calendar month a yearly schedule bills in (None = month of creation).
    schedule_month: int | None = Field(None, ge=1, le=12)
    # Which month within each quarter a quarterly schedule bills in.
    quarter_month: int = Field(1, ge=1, le=3)
    currency_code: str = Field("USD", max_length=3)
    payment_terms_days: int = Field(30, ge=0, le=365)
    notes: str | None = Field(None, max_length=10000)
    use_default_notes: bool = True
    line_items: list[LineItemCreate] | None = None
    show_payment_instructions: bool = True
    selected_payment_methods: list[str] | None = Field(None, max_length=50)
    auto_email_enabled: bool = False
    email_subject_template: str | None = Field(None, max_length=500)
    email_body_template: str | None = Field(None, max_length=10000)
    tax_enabled: bool | None = None
    tax_rate: Decimal | None = Field(None, ge=0, le=100)
    tax_name: str | None = Field(None, max_length=50)
    next_invoice_date: date | None = None

    @model_validator(mode="after")
    def validate_schedule_day(self) -> "RecurringScheduleCreate":
        _validate_schedule_day_for_frequency(self.frequency, self.schedule_day)
        return self


class RecurringScheduleUpdate(BaseModel):
    """Update recurring schedule request."""

    name: str | None = Field(None, min_length=1, max_length=255)
    frequency: str | None = Field(None, pattern="^(daily|weekly|monthly|quarterly|yearly)$")
    schedule_day: int | None = Field(None, ge=0, le=31)
    schedule_month: int | None = Field(None, ge=1, le=12)
    quarter_month: int | None = Field(None, ge=1, le=3)
    currency_code: str | None = Field(None, max_length=3)
    payment_terms_days: int | None = Field(None, ge=0, le=365)
    notes: str | None = Field(None, max_length=10000)
    use_default_notes: bool | None = None
    line_items: list[LineItemCreate] | None = None
    show_payment_instructions: bool | None = None
    selected_payment_methods: list[str] | None = Field(None, max_length=50)
    auto_email_enabled: bool | None = None
    email_subject_template: str | None = Field(None, max_length=500)
    email_body_template: str | None = Field(None, max_length=10000)
    tax_enabled: bool | None = None
    tax_rate: Decimal | None = Field(None, ge=0, le=100)
    tax_name: str | None = Field(None, max_length=50)
    is_active: bool | None = None
    next_invoice_date: date | None = None

    @model_validator(mode="after")
    def validate_schedule_day(self) -> "RecurringScheduleUpdate":
        _validate_schedule_day_for_frequency(self.frequency, self.schedule_day)
        return self


def _schedule_to_dict(schedule: RecurringSchedule) -> dict:
    """Convert schedule to response dict."""
    return serialize_recurring_schedule(schedule, json_ready=True)


@router.get("")
@limiter.limit("60/minute")
async def list_schedules(
    request: Request,
    client_id: int | None = None,
    active_only: bool = True,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """List recurring schedules."""
    schedules = await RecurringService.list_schedules(
        session, client_id=client_id, active_only=active_only
    )
    return [_schedule_to_dict(s) for s in schedules]


@router.post("", status_code=201)
@limiter.limit("30/minute")
async def create_schedule(
    request: Request,
    data: RecurringScheduleCreate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a new recurring schedule."""
    try:
        line_items = None
        if data.line_items:
            line_items = [item.model_dump() for item in data.line_items]

        schedule = await RecurringService.create_schedule(
            session,
            client_id=data.client_id,
            name=data.name,
            frequency=data.frequency,
            schedule_day=data.schedule_day,
            schedule_month=data.schedule_month,
            quarter_month=data.quarter_month,
            currency_code=data.currency_code,
            payment_terms_days=data.payment_terms_days,
            notes=data.notes,
            use_default_notes=int(data.use_default_notes),
            line_items=line_items,
            show_payment_instructions=int(data.show_payment_instructions),
            selected_payment_methods=data.selected_payment_methods,
            auto_email_enabled=int(data.auto_email_enabled),
            email_subject_template=data.email_subject_template or None,
            email_body_template=data.email_body_template or None,
            tax_enabled=int(data.tax_enabled) if data.tax_enabled is not None else None,
            tax_rate=data.tax_rate,
            tax_name=data.tax_name,
            next_invoice_date=data.next_invoice_date,
        )
        return _schedule_to_dict(schedule)
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{schedule_id}")
@limiter.limit("60/minute")
async def get_schedule(
    request: Request,
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get a recurring schedule by ID."""
    schedule = await RecurringService.get_schedule(session, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _schedule_to_dict(schedule)


@router.put("/{schedule_id}")
@limiter.limit("30/minute")
async def update_schedule(
    request: Request,
    schedule_id: int,
    data: RecurringScheduleUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update a recurring schedule."""
    update_data = data.model_dump(exclude_unset=True)

    if "line_items" in update_data and update_data["line_items"] is not None:
        update_data["line_items"] = [
            item if isinstance(item, dict) else item.model_dump()
            for item in update_data["line_items"]
        ]

    # SQLite stores booleans as ints.
    for bool_field in (
        "tax_enabled",
        "is_active",
        "use_default_notes",
        "show_payment_instructions",
        "auto_email_enabled",
    ):
        if update_data.get(bool_field) is not None:
            update_data[bool_field] = int(update_data[bool_field])

    try:
        schedule = await RecurringService.update_schedule(session, schedule_id, **update_data)
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _schedule_to_dict(schedule)


@router.delete("/{schedule_id}", status_code=204)
@limiter.limit("30/minute")
async def delete_schedule(
    request: Request,
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a recurring schedule."""
    deleted = await RecurringService.delete_schedule(session, schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Schedule not found")


@router.post("/{schedule_id}/pause")
@limiter.limit("30/minute")
async def pause_schedule(
    request: Request,
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Pause a recurring schedule."""
    success = await RecurringService.pause_schedule(session, schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule = await RecurringService.get_schedule(session, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _schedule_to_dict(schedule)


@router.post("/{schedule_id}/resume")
@limiter.limit("30/minute")
async def resume_schedule(
    request: Request,
    schedule_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Resume a paused recurring schedule."""
    success = await RecurringService.resume_schedule(session, schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule = await RecurringService.get_schedule(session, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _schedule_to_dict(schedule)


@router.post("/{schedule_id}/trigger")
@limiter.limit("10/minute")  # Stricter limit as this creates invoices
async def trigger_schedule(
    request: Request,
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
