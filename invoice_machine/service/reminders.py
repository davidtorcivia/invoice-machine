"""Provider-independent, idempotent invoice payment reminders."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.config import get_settings
from invoice_machine.database import BusinessProfile, Invoice, ReminderDelivery
from invoice_machine.email import expand_template
from invoice_machine.service.common import format_currency
from invoice_machine.service.email import send_invoice_email
from invoice_machine.service.payments import PaymentService
from invoice_machine.utils import ensure_utc, utc_now

DEFAULT_REMINDER_SUBJECT = "Payment reminder: {document_type} {invoice_number}"
DEFAULT_REMINDER_BODY = """Hello {client_name},

This is a friendly reminder that {document_type_lower} {invoice_number} has an outstanding balance of {outstanding} and was due on {due_date}.

{payment_link_line}

Thank you,
{your_name}"""

_REMINDER_CLAIM_TIMEOUT = timedelta(minutes=15)


class ReminderService:
    @staticmethod
    def parse_offsets(raw: str | list[int]) -> list[int]:
        try:
            values = json.loads(raw) if isinstance(raw, str) else raw
            offsets = sorted({int(value) for value in values})
        except (json.JSONDecodeError, TypeError, ValueError):
            raise ValueError("Reminder offsets must be a JSON array of whole days") from None
        if not offsets or len(offsets) > 20 or any(value < -365 or value > 365 for value in offsets):
            raise ValueError("Provide 1-20 reminder offsets between -365 and 365 days")
        return offsets

    @staticmethod
    def validate_timezone(name: str) -> str:
        try:
            ZoneInfo(name)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Unknown timezone: {name}") from None
        return name

    @staticmethod
    async def render(
        session: AsyncSession, invoice: Invoice, profile: BusinessProfile
    ) -> dict:
        summary = await PaymentService.payment_summary(session, invoice)
        payment_url = None
        if (
            profile.online_payments_enabled
            and invoice.online_payment_enabled
            and invoice.payment_token
            and invoice.document_type == "invoice"
            and invoice.status in {"sent", "overdue", "partially_paid"}
            and invoice.deleted_at is None
            and summary["outstanding"] > 0
        ):
            payment_url = (
                f"{get_settings().app_base_url.rstrip('/')}/pay/{invoice.payment_token}"
            )

        subject = expand_template(
            profile.reminder_subject_template or DEFAULT_REMINDER_SUBJECT,
            invoice,
            profile,
        )
        body = expand_template(
            profile.reminder_body_template or DEFAULT_REMINDER_BODY,
            invoice,
            profile,
        )
        replacements = {
            "{outstanding}": format_currency(
                Decimal(summary["outstanding"]), invoice.currency_code
            ),
            "{amount_paid}": format_currency(Decimal(summary["paid"]), invoice.currency_code),
            "{payment_url}": payment_url or "",
            "{payment_link_line}": (
                f"Pay securely online: {payment_url}" if payment_url else ""
            ),
        }
        for placeholder, value in replacements.items():
            subject = subject.replace(placeholder, value)
            body = body.replace(placeholder, value)
        return {"subject": subject, "body": body, "payment_url": payment_url}

    @staticmethod
    async def list_deliveries(
        session: AsyncSession, invoice_id: int
    ) -> list[ReminderDelivery]:
        result = await session.execute(
            select(ReminderDelivery)
            .where(ReminderDelivery.invoice_id == invoice_id)
            .order_by(ReminderDelivery.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def process_due_reminders(
        session: AsyncSession,
        *,
        now: datetime | None = None,
        ignore_send_hour: bool = False,
    ) -> list[dict]:
        profile = await BusinessProfile.get_or_create(session)
        if not profile.reminders_enabled:
            return []
        if not profile.smtp_enabled:
            return [{"skipped": True, "reason": "SMTP is not enabled"}]

        timezone = ZoneInfo(ReminderService.validate_timezone(profile.business_timezone or "UTC"))
        run_now = ensure_utc(now) or utc_now()
        local_now = run_now.astimezone(timezone)
        if not ignore_send_hour and local_now.hour < int(profile.reminder_send_hour or 0):
            return []
        today = local_now.date()
        offsets = ReminderService.parse_offsets(profile.reminder_offsets)

        result = await session.execute(
            select(Invoice).where(
                Invoice.deleted_at.is_(None),
                Invoice.document_type == "invoice",
                Invoice.reminders_enabled == 1,
                Invoice.status.in_(["sent", "overdue", "partially_paid"]),
                Invoice.due_date.is_not(None),
                Invoice.client_email.is_not(None),
            )
        )
        invoices = list(result.scalars().all())
        outcomes: list[dict] = []

        for invoice in invoices:
            days_from_due = (today - invoice.due_date).days
            eligible = [offset for offset in offsets if offset <= days_from_due]
            if not eligible:
                continue
            offset = max(eligible)
            existing = (
                await session.execute(
                    select(ReminderDelivery).where(
                        ReminderDelivery.invoice_id == invoice.id,
                        ReminderDelivery.due_date == invoice.due_date,
                        ReminderDelivery.offset_days == offset,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                claim = await session.execute(
                    update(ReminderDelivery)
                    .where(
                        ReminderDelivery.id == existing.id,
                        or_(
                            ReminderDelivery.status == "failed",
                            and_(
                                ReminderDelivery.status == "sending",
                                or_(
                                    ReminderDelivery.claimed_at.is_(None),
                                    ReminderDelivery.claimed_at
                                    <= run_now - _REMINDER_CLAIM_TIMEOUT,
                                ),
                            ),
                        ),
                    )
                    .values(
                        recipient=invoice.client_email,
                        status="sending",
                        error=None,
                        claimed_at=run_now,
                    )
                    .execution_options(synchronize_session=False)
                )
                await session.commit()
                if claim.rowcount != 1:
                    continue
                delivery = await session.get(
                    ReminderDelivery, existing.id, populate_existing=True
                )
            else:
                delivery = ReminderDelivery(
                    invoice_id=invoice.id,
                    due_date=invoice.due_date,
                    offset_days=offset,
                    recipient=invoice.client_email,
                    status="sending",
                    claimed_at=run_now,
                )
                session.add(delivery)
                try:
                    # The unique key is the claim for first delivery. A racing
                    # worker that loses the insert must not send the email.
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    continue

            rendered = await ReminderService.render(session, invoice, profile)
            send_result = await send_invoice_email(
                session,
                invoice.id,
                recipient_email=invoice.client_email,
                subject=rendered["subject"],
                body=rendered["body"],
            )
            delivery = await session.get(ReminderDelivery, delivery.id)
            if send_result.get("success"):
                delivery.status = "sent"
                delivery.sent_at = utc_now()
                delivery.error = None
            else:
                delivery.status = "failed"
                delivery.error = str(send_result.get("error", "Unknown email failure"))[:2000]
            await session.commit()
            outcomes.append(
                {
                    "invoice_id": invoice.id,
                    "offset_days": offset,
                    "status": delivery.status,
                    "error": delivery.error,
                }
            )
        return outcomes
