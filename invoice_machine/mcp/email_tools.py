"""Email MCP tools."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context, Elicit, Resolve
from mcp.server.mcpserver.exceptions import ToolError

from invoice_machine.database import BusinessProfile
from invoice_machine.services import InvoiceService
from invoice_machine.utils import utc_now

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
    from invoice_machine.service.email import send_invoice_email as send_invoice_email_service

    ensure_confirmed(confirmation, "Sending this invoice")

    async with get_session() as session:
        return await send_invoice_email_service(
            session,
            invoice_id,
            recipient_email=recipient_email,
            subject=subject,
            body=body,
        )


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

        email_service = EmailService(profile)
        return await email_service.test_connection()


@mcp.tool(annotations=READ_ONLY)
async def get_email_templates() -> dict:
    """Get the email templates for invoice/quote emails, plus the placeholders."""
    from invoice_machine.email import DEFAULT_BODY_TEMPLATE, DEFAULT_SUBJECT_TEMPLATE

    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        return {
            "email_subject_template": profile.email_subject_template,
            "email_body_template": profile.email_body_template,
            "available_placeholders": [
                "{invoice_number}",
                "{quote_number}",
                "{document_type}",
                "{document_type_lower}",
                "{client_name}",
                "{client_business_name}",
                "{client_email}",
                "{total}",
                "{amount}",
                "{subtotal}",
                "{due_date}",
                "{issue_date}",
                "{your_name}",
                "{business_name}",
            ],
            "default_subject": DEFAULT_SUBJECT_TEMPLATE,
            "default_body": DEFAULT_BODY_TEMPLATE,
        }


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
        profile = await BusinessProfile.get_or_create(session)

        if email_subject_template is not None:
            profile.email_subject_template = email_subject_template or None
        if email_body_template is not None:
            profile.email_body_template = email_body_template or None

        profile.updated_at = utc_now()
        await session.commit()
        await session.refresh(profile)

        return {
            "email_subject_template": profile.email_subject_template,
            "email_body_template": profile.email_body_template,
        }


@mcp.tool(annotations=READ_ONLY)
async def preview_invoice_email(
    invoice_id: int,
    subject_template: str | None = None,
    body_template: str | None = None,
) -> dict:
    """Preview an invoice email with its templates expanded."""
    from invoice_machine.email import (
        DEFAULT_BODY_TEMPLATE,
        DEFAULT_SUBJECT_TEMPLATE,
        expand_template,
    )

    async with get_session() as session:
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            raise ToolError(f"Invoice {invoice_id} not found")

        profile = await BusinessProfile.get_or_create(session)

        subj_tmpl = (
            subject_template
            if subject_template is not None
            else (profile.email_subject_template or DEFAULT_SUBJECT_TEMPLATE)
        )
        body_tmpl = (
            body_template
            if body_template is not None
            else (profile.email_body_template or DEFAULT_BODY_TEMPLATE)
        )

        subject = expand_template(subj_tmpl, invoice, profile)
        body = expand_template(body_tmpl, invoice, profile)

        return {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "recipient_email": invoice.client_email,
            "subject": subject,
            "body": body,
            "subject_template_used": subj_tmpl,
            "body_template_used": body_tmpl,
        }
