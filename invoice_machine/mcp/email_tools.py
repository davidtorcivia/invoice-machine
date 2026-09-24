"""Email MCP tools."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context, Elicit, Resolve
from mcp.server.mcpserver.exceptions import ToolError

from invoice_machine.database import BusinessProfile
from invoice_machine.service import email as email_service
from invoice_machine.service.invoices import InvoiceService

from .annotations import OUTWARD, READ_ONLY, READ_ONLY_REMOTE, UPDATE
from .confirmations import Confirmation, confirmed, ensure_confirmed
from .context import get_session, mcp


async def _confirm_send(
    invoice_id: int,
    recipient_email: str | None,
    ctx: Context,
) -> Confirmation | Elicit[Confirmation]:
    """Ask before an invoice leaves for a real inbox."""
    async with get_session() as session:
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        number = invoice.invoice_number if invoice else invoice_id
        # Mirror EmailService.send_invoice's own resolution so the address
        # quoted in the prompt is the one that will actually receive the mail.
        to = recipient_email or (invoice.client_email if invoice else None)

    return confirmed(
        ctx,
        f"Send invoice {number} to {to or 'the client on file'}? "
        "The email cannot be recalled once sent.",
    )


@mcp.tool(annotations=OUTWARD)
async def send_invoice_email(
    invoice_id: int,
    confirmation: Annotated[Confirmation, Resolve(_confirm_send)],
    recipient_email: str | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> dict:
    """
    Send an invoice PDF via email.

    Requires SMTP to be configured in business profile settings. Asks the user
    to confirm before sending, where the client supports it. The recipient
    defaults to the client's email, subject and body to the saved templates.
    """
    ensure_confirmed(confirmation, "Sending this invoice")

    async with get_session() as session:
        result = await email_service.send_invoice_email(
            session,
            invoice_id,
            recipient_email=recipient_email,
            subject=subject,
            body=body,
        )
    if result.get("not_found"):
        raise ToolError(result["error"])
    return result


@mcp.tool(annotations=READ_ONLY_REMOTE)
async def test_smtp_connection() -> dict:
    """Test SMTP connection without sending an email."""
    from invoice_machine.email import EmailService

    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        if not profile.smtp_enabled:
            return {
                "success": False,
                "error": "SMTP is not enabled. Configure SMTP settings first.",
            }

        return await EmailService(profile).test_connection()


@mcp.tool(annotations=READ_ONLY)
async def get_email_templates() -> dict:
    """Get the email templates for invoice/quote emails, plus the placeholders."""
    async with get_session() as session:
        return email_service.email_templates(await BusinessProfile.get_or_create(session))


@mcp.tool(annotations=UPDATE)
async def update_email_templates(
    email_subject_template: str | None = None,
    email_body_template: str | None = None,
) -> dict:
    """
    Update email templates for invoice/quote emails.

    Use placeholders like {invoice_number}, {client_name}, {total}, {due_date} etc.
    Set a template to empty string to clear it (will use defaults).
    """
    async with get_session() as session:
        return await email_service.update_email_templates(
            session, email_subject_template, email_body_template
        )


@mcp.tool(annotations=READ_ONLY)
async def preview_invoice_email(
    invoice_id: int,
    subject_template: str | None = None,
    body_template: str | None = None,
) -> dict:
    """Preview an invoice email with its templates expanded."""
    async with get_session() as session:
        preview = await email_service.preview_invoice_email(
            session, invoice_id, subject_template, body_template
        )
        if preview is None:
            raise ToolError(f"Invoice {invoice_id} not found")
        return preview
