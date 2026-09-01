"""Automated payment reminders for unpaid invoices.

Reminders fire on configurable day-offsets relative to an invoice's due date
(negative = before due, positive = after). Each offset is recorded on the invoice
once sent, so re-running the sweep — after a restart, a manual trigger, or twice
in one day — can never re-send the same reminder.
"""

from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import BusinessProfile, Invoice
from invoice_machine.utils import utc_now

logger = logging.getLogger(__name__)

# Sensible starting schedule if reminders are enabled without explicit offsets:
# a courtesy nudge 3 days before, then escalating chases after the due date.
DEFAULT_REMINDER_OFFSETS = (-3, 1, 7, 14)

# Guard rails on configured offsets (roughly a year either side).
MIN_OFFSET = -365
MAX_OFFSET = 365


def validate_timezone(name: str) -> str:
    """Validate an IANA timezone name, returning it unchanged."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    candidate = (name or "UTC").strip() or "UTC"
    try:
        ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise ValueError(f"Unknown timezone: {candidate}") from None
    return candidate


def business_now(profile: BusinessProfile | None):
    """Current time in the business's configured timezone."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    name = (profile.business_timezone if profile else None) or "UTC"
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        # A bad stored value must not stop reminders going out.
        logger.warning("Unknown business timezone %r; falling back to UTC", name)
        zone = ZoneInfo("UTC")
    return utc_now().astimezone(zone)


DEFAULT_REMINDER_SUBJECT = "Reminder: {document_type} {invoice_number} ({due_status})"
DEFAULT_REMINDER_BODY = """Dear {client_name},

This is a friendly reminder about {document_type_lower} {invoice_number}, {due_status}.

Amount outstanding: {amount_due}
Due date: {due_date}

If you have already sent payment, please disregard this message.

Best regards,
{your_name}"""

# Statuses a reminder may be sent for. Drafts were never issued, quotes are not
# owed, cancelled is void, and paid needs no chasing.
REMINDABLE_STATUSES = ("sent", "overdue")


def validate_reminder_offsets(offsets: list[int]) -> list[int]:
    """Validate and normalize a reminder schedule (sorted, de-duplicated)."""
    if len(offsets) > 10:
        raise ValueError("At most 10 reminder offsets are supported")
    normalized = set()
    for raw in offsets:
        try:
            offset = int(raw)
        except (TypeError, ValueError):
            raise ValueError("Reminder offsets must be whole numbers of days") from None
        if not (MIN_OFFSET <= offset <= MAX_OFFSET):
            raise ValueError(f"Reminder offsets must be between {MIN_OFFSET} and {MAX_OFFSET} days")
        normalized.add(offset)
    return sorted(normalized)


def _due_status_text(days_relative: int) -> str:
    """Human phrasing for how far from due the invoice is."""
    if days_relative < 0:
        days = abs(days_relative)
        return f"due in {days} day{'s' if days != 1 else ''}"
    if days_relative == 0:
        return "due today"
    return f"{days_relative} day{'s' if days_relative != 1 else ''} overdue"


def build_reminder_content(
    invoice: Invoice,
    profile: BusinessProfile,
    days_relative: int,
) -> tuple[str, str]:
    """Expand the reminder subject/body templates for an invoice."""
    from invoice_machine.email import expand_template
    from invoice_machine.service.common import format_currency

    subject_template = profile.reminder_subject_template or DEFAULT_REMINDER_SUBJECT
    body_template = profile.reminder_body_template or DEFAULT_REMINDER_BODY

    subject = expand_template(subject_template, invoice, profile)
    body = expand_template(body_template, invoice, profile)

    # Reminder-only placeholders, applied after the shared invoice expansion.
    extras = {
        "{due_status}": _due_status_text(days_relative),
        "{amount_due}": format_currency(invoice.amount_due, invoice.currency_code),
        "{days_overdue}": str(max(days_relative, 0)),
    }
    for placeholder, value in extras.items():
        subject = subject.replace(placeholder, value)
        body = body.replace(placeholder, value)

    return subject, body


def due_offsets_for(invoice: Invoice, offsets: list[int], today: date) -> list[int]:
    """Offsets that have come due for this invoice and not yet been sent.

    Every passed-but-unsent offset is returned, newest last. Only the last one is
    actually emailed; the earlier ones are *superseded* and get marked as sent
    without being delivered (see :func:`send_due_reminders`). That matters when
    reminders are switched on for an already-overdue invoice: the client should
    get one current chase, not four at once — and not the stale backlog dripped
    out in reverse over the following days.
    """
    if not invoice.due_date:
        return []

    already_sent = set(invoice.reminders_sent_list)
    days_relative = (today - invoice.due_date).days

    return [offset for offset in offsets if offset not in already_sent and offset <= days_relative]


async def send_due_reminders(session: AsyncSession, today: date | None = None) -> list[dict]:
    """Send every reminder that is due today. Returns one result dict per attempt.

    "Today" is the date in the business's own timezone. Using the UTC date would
    misjudge how overdue an invoice is by a day for anyone far enough from UTC.
    """
    from invoice_machine.service.common import run_per_row
    from invoice_machine.service.email import send_invoice_email

    maybe_profile = await BusinessProfile.get(session)
    today = today or business_now(maybe_profile).date()

    if not maybe_profile or not maybe_profile.reminders_enabled:
        return []
    # Non-optional binding: the nested send/failure handlers close over it.
    profile = maybe_profile
    if not profile.smtp_enabled:
        logger.warning("Payment reminders are enabled but SMTP is not configured; skipping.")
        return []

    offsets = profile.reminder_offsets_list or list(DEFAULT_REMINDER_OFFSETS)

    candidates = (
        (
            await session.execute(
                select(Invoice).where(
                    Invoice.document_type == "invoice",
                    Invoice.deleted_at.is_(None),
                    Invoice.status.in_(REMINDABLE_STATUSES),
                    Invoice.due_date.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    results: list[dict] = []
    # Set before the risky part so the error path can report which reminder failed.
    pending: dict = {}

    async def send_one(invoice: Invoice) -> None:
        pending.clear()
        if invoice.due_date is None or invoice.amount_due <= 0:
            return
        if not (invoice.client_email or "").strip():
            return

        due_offsets = due_offsets_for(invoice, offsets, today)
        if not due_offsets:
            return

        # Send only the most recent offset; the earlier ones have been overtaken
        # and are recorded as sent so they cannot fire on later days.
        offset = due_offsets[-1]
        superseded = due_offsets[:-1]
        days_relative = (today - invoice.due_date).days
        invoice_id = invoice.id
        pending.update(invoice_number=invoice.invoice_number, offset=offset)

        subject, body = build_reminder_content(invoice, profile, days_relative)
        result = await send_invoice_email(session, invoice_id, subject=subject, body=body)

        if result.get("success"):
            # Record the offsets only on a confirmed send, so a transient SMTP
            # failure retries tomorrow instead of being silently swallowed.
            # Core UPDATE with updated_at pinned: the column's onupdate would
            # otherwise mark the invoice stale and force a PDF re-render.
            sent = sorted({*invoice.reminders_sent_list, offset, *superseded})
            await session.execute(
                update(Invoice)
                .where(Invoice.id == invoice_id)
                .values(
                    reminders_sent=json.dumps(sent),
                    last_reminder_sent_at=utc_now(),
                    updated_at=invoice.updated_at,
                )
            )
            await session.commit()
            session.expire(invoice)

        results.append(
            {
                "invoice_id": invoice_id,
                "invoice_number": pending["invoice_number"],
                "offset": offset,
                "superseded_offsets": superseded,
                "days_relative": days_relative,
                "recipient": result.get("recipient"),
                "success": bool(result.get("success")),
                **({"error": result["error"]} if result.get("error") else {}),
            }
        )

    async def record_failure(invoice_id: int, exc: Exception) -> None:
        nonlocal profile
        # The rollback expired the profile loaded above; the next reminder needs it.
        # The singleton row cannot vanish, so keep the old object if it comes back
        # empty rather than failing the run from inside the error handler.
        profile = await BusinessProfile.get(session) or profile
        logger.error(
            "Reminder for invoice %s failed: %s", pending.get("invoice_number"), exc, exc_info=True
        )
        results.append(
            {
                "invoice_id": invoice_id,
                "invoice_number": pending.get("invoice_number"),
                "offset": pending.get("offset"),
                "success": False,
                "error": str(exc),
            }
        )

    await run_per_row(
        session, Invoice, [invoice.id for invoice in candidates], send_one, record_failure
    )

    return results
