"""Invoice reminder MCP tools."""

from __future__ import annotations

from invoice_machine.database import BusinessProfile, Invoice
from invoice_machine.service.reminders import ReminderService

from .context import get_session, mcp


@mcp.tool()
async def preview_invoice_reminder(invoice_id: int) -> dict:
    """Preview the subject and body of an invoice reminder without sending it."""
    async with get_session() as session:
        invoice = await session.get(Invoice, invoice_id)
        if not invoice or invoice.deleted_at is not None:
            raise ValueError("Invoice not found")
        profile = await BusinessProfile.get_or_create(session)
        return await ReminderService.render(session, invoice, profile)


@mcp.tool()
async def process_due_invoice_reminders() -> list[dict]:
    """Send reminders due now. Global reminder and SMTP settings must be enabled."""
    async with get_session() as session:
        return await ReminderService.process_due_reminders(
            session, ignore_send_hour=True
        )
