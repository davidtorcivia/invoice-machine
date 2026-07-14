"""Payment reminder settings, previews, logs, and manual processing."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import BusinessProfile, Invoice, get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.service.reminders import ReminderService

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


class ReminderSettingsUpdate(BaseModel):
    reminders_enabled: bool | None = None
    reminder_offsets: list[int] | None = Field(None, min_length=1, max_length=20)
    reminder_subject_template: str | None = Field(None, max_length=500)
    reminder_body_template: str | None = Field(None, max_length=10000)
    business_timezone: str | None = Field(None, max_length=100)
    reminder_send_hour: int | None = Field(None, ge=0, le=23)


def _settings_response(profile: BusinessProfile) -> dict:
    return {
        "reminders_enabled": bool(profile.reminders_enabled),
        "reminder_offsets": ReminderService.parse_offsets(profile.reminder_offsets),
        "reminder_subject_template": profile.reminder_subject_template,
        "reminder_body_template": profile.reminder_body_template,
        "business_timezone": profile.business_timezone,
        "reminder_send_hour": profile.reminder_send_hour,
    }


@router.get("/settings")
async def get_reminder_settings(session: AsyncSession = Depends(get_session)) -> dict:
    return _settings_response(await BusinessProfile.get_or_create(session))


@router.put("/settings")
@limiter.limit("20/minute")
async def update_reminder_settings(
    request: Request,
    updates: ReminderSettingsUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    profile = await BusinessProfile.get_or_create(session)
    values = updates.model_dump(exclude_unset=True)
    try:
        if "reminder_offsets" in values:
            profile.reminder_offsets = json.dumps(
                ReminderService.parse_offsets(values["reminder_offsets"])
            )
        if "business_timezone" in values:
            profile.business_timezone = ReminderService.validate_timezone(
                values["business_timezone"] or "UTC"
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    for field in (
        "reminder_subject_template",
        "reminder_body_template",
        "reminder_send_hour",
    ):
        if field in values:
            setattr(profile, field, values[field])
    if "reminders_enabled" in values:
        profile.reminders_enabled = 1 if values["reminders_enabled"] else 0
    await session.commit()
    await session.refresh(profile)
    return _settings_response(profile)


@router.get("/invoices/{invoice_id}/preview")
async def preview_reminder(
    invoice_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    invoice = await session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    profile = await BusinessProfile.get_or_create(session)
    return await ReminderService.render(session, invoice, profile)


@router.get("/invoices/{invoice_id}/deliveries")
async def list_reminder_deliveries(
    invoice_id: int, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    deliveries = await ReminderService.list_deliveries(session, invoice_id)
    return [
        {
            "id": delivery.id,
            "invoice_id": delivery.invoice_id,
            "due_date": delivery.due_date.isoformat(),
            "offset_days": delivery.offset_days,
            "recipient": delivery.recipient,
            "status": delivery.status,
            "error": delivery.error,
            "sent_at": delivery.sent_at.isoformat() if delivery.sent_at else None,
            "created_at": delivery.created_at.isoformat(),
        }
        for delivery in deliveries
    ]


@router.post("/process")
@limiter.limit("5/minute")
async def process_reminders_now(
    request: Request, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    return await ReminderService.process_due_reminders(
        session, ignore_send_hour=True
    )
