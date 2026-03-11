"""Email MCP tools."""

from __future__ import annotations

from invoice_machine.database import BusinessProfile
from invoice_machine.services import InvoiceService
from invoice_machine.utils import utc_now

from .context import get_session, mcp


@mcp.tool()
async def send_invoice_email(
    invoice_id: int,
    recipient_email: str | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> dict:
    """
    Send an invoice PDF via email.

    Requires SMTP to be configured in business profile settings.

    Args:
        invoice_id: The invoice ID to send
        recipient_email: Override recipient (defaults to client's email)
        subject: Override email subject (defaults to "Invoice {number}")
        body: Override email body (defaults to friendly message with invoice details)

    Returns:
        Success status and details
    """
    from invoice_machine.email import EmailService
    from invoice_machine.pdf.generator import generate_pdf

    async with get_session() as session:
        # Get business profile for SMTP settings
        profile = await BusinessProfile.get_or_create(session)

        if not profile.smtp_enabled:
            return {
                "success": False,
                "error": "SMTP is not enabled. Configure SMTP settings in business profile first.",
            }

        # Get invoice
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            return {"success": False, "error": f"Invoice {invoice_id} not found"}

        # Generate PDF if needed
        if invoice.needs_pdf_regeneration:
            pdf_path = await generate_pdf(session, invoice)
            invoice.pdf_path = pdf_path
            invoice.pdf_generated_at = utc_now()
            await session.commit()

        # Send email
        email_service = EmailService(profile)
        result = await email_service.send_invoice(
            invoice,
            recipient_email=recipient_email,
            subject=subject,
            body=body,
        )

        # Update invoice status if sent successfully
        if result.get("success") and invoice.status == "draft":
            invoice.status = "sent"
            await session.commit()
            result["status_updated"] = "sent"

        return result


@mcp.tool()
async def test_smtp_connection() -> dict:
    """
    Test SMTP connection without sending an email.

    Returns:
        Success status and connection details
    """
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


@mcp.tool()
async def get_email_templates() -> dict:
    """
    Get the current email templates for invoice/quote emails.

    Returns:
        Current email subject and body templates, plus available placeholders.
    """
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


@mcp.tool()
async def update_email_templates(
    email_subject_template: str | None = None,
    email_body_template: str | None = None,
) -> dict:
    """
    Update email templates for invoice/quote emails.

    Use placeholders like {invoice_number}, {client_name}, {total}, {due_date} etc.
    Set a template to empty string to clear it (will use defaults).

    Args:
        email_subject_template: Template for email subject
        email_body_template: Template for email body

    Returns:
        Updated email templates
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


@mcp.tool()
async def preview_invoice_email(
    invoice_id: int,
    subject_template: str | None = None,
    body_template: str | None = None,
) -> dict:
    """
    Preview what an invoice email will look like with template expansion.

    Args:
        invoice_id: The invoice ID to preview email for
        subject_template: Optional override for subject template
        body_template: Optional override for body template

    Returns:
        Expanded subject, body, recipient email, and available placeholders
    """
    from invoice_machine.email import (
        DEFAULT_BODY_TEMPLATE,
        DEFAULT_SUBJECT_TEMPLATE,
        expand_template,
    )

    async with get_session() as session:
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            return {"error": f"Invoice {invoice_id} not found"}

        profile = await BusinessProfile.get_or_create(session)

        # Use provided templates, fall back to saved templates, then defaults
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



