"""Invoice reminder MCP tools."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context, Elicit, Resolve

from invoice_machine.database import BusinessProfile, Invoice
from invoice_machine.service.reminders import ReminderService

from .annotations import OUTWARD, READ_ONLY
from .confirmations import Confirmation, confirmed, ensure_confirmed
from .context import get_session, mcp


@mcp.tool(annotations=READ_ONLY)
async def preview_invoice_reminder(invoice_id: int) -> dict:
    """Preview the subject and body of an invoice reminder without sending it."""
    async with get_session() as session:
        invoice = await session.get(Invoice, invoice_id)
        if not invoice or invoice.deleted_at is not None:
            raise ValueError("Invoice not found")
        profile = await BusinessProfile.get_or_create(session)
        return await ReminderService.render(session, invoice, profile)


async def _confirm_reminder_run(ctx: Context) -> Confirmation | Elicit[Confirmation]:
    """Ask before a batch send.

    Deliberately does not quote a count. Which invoices are due lives inside
    ReminderService.process_due_reminders, and re-deriving it here would either
    duplicate that logic or drift from it - a confirmation that promises "3
    emails" and sends 4 is worse than one that does not promise a number.
    """
    return confirmed(
        ctx,
        "Send invoice reminder emails to every client with a reminder due now? "
        "They cannot be recalled once sent.",
    )


@mcp.tool(annotations=OUTWARD)
async def process_due_invoice_reminders(
    confirmation: Annotated[Confirmation, Resolve(_confirm_reminder_run)],
) -> list[dict]:
    """Send reminders due now. Global reminder and SMTP settings must be enabled.

    Asks the user to confirm before sending, where the client supports it.
    """
    ensure_confirmed(confirmation, "Sending due reminders")

    async with get_session() as session:
        return await ReminderService.process_due_reminders(
            session, ignore_send_hour=True
        )
