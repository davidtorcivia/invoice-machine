"""Invoice email flows shared by the REST API and MCP tools.

Centralizes sending, previews and template settings so the two surfaces cannot
drift: SMTP-enabled check, PDF freshness, delivery, the draft -> sent
transition, and the template length caps all live here.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import BusinessProfile
from invoice_machine.email import (
    DEFAULT_BODY_TEMPLATE,
    DEFAULT_SUBJECT_TEMPLATE,
    TEMPLATE_PLACEHOLDERS,
    EmailService,
    expand_template,
)
from invoice_machine.service.invoices import InvoiceService, apply_status
from invoice_machine.service.profile import EmailTemplatesUpdate


async def send_invoice_email(
    session: AsyncSession,
    invoice_id: int,
    *,
    recipient_email: str | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> dict:
    """Send an invoice's PDF by email.

    Returns a result dict. On failure it includes ``success: False`` and an
    ``error`` message; ``not_found: True`` distinguishes a missing invoice so the
    REST layer can map it to 404. The PDF is (re)generated when missing or stale
    so a changed invoice is never emailed with an out-of-date document, and a
    successful send moves a draft to ``sent``, or ``paid`` when payments already
    cover it (recorded as ``status_updated``).
    """
    # Deferred like every other caller: importing WeasyPrint needs its system libraries.
    from invoice_machine.pdf.generator import store_invoice_pdf

    invoice = await InvoiceService.get_invoice(session, invoice_id)
    if not invoice:
        return {"success": False, "error": f"Invoice {invoice_id} not found", "not_found": True}

    profile = await BusinessProfile.get_or_create(session)
    if not profile.smtp_enabled:
        return {
            "success": False,
            "error": "SMTP is not enabled. Configure SMTP settings first.",
        }

    # Never email a stale or missing PDF.
    await store_invoice_pdf(session, invoice)

    email_service = EmailService(profile)
    result = await email_service.send_invoice(
        invoice,
        recipient_email=recipient_email,
        subject=subject,
        body=body,
    )

    if result.get("success") and invoice.status == "draft":
        await apply_status(session, invoice, "sent")
        await session.commit()
        result["status_updated"] = invoice.status

    return result


def email_templates(profile: BusinessProfile) -> dict:
    """The stored templates, the built-in defaults, and the placeholders they accept."""
    return {
        "email_subject_template": profile.email_subject_template,
        "email_body_template": profile.email_body_template,
        "available_placeholders": list(TEMPLATE_PLACEHOLDERS),
        "default_subject": DEFAULT_SUBJECT_TEMPLATE,
        "default_body": DEFAULT_BODY_TEMPLATE,
    }


async def update_email_templates(
    session: AsyncSession, subject_template: str | None, body_template: str | None
) -> dict:
    """Store the templates; an empty string clears one back to the built-in default."""
    # The REST request caps, raised as a ValidationError (a ValueError) for MCP.
    EmailTemplatesUpdate(email_subject_template=subject_template, email_body_template=body_template)
    profile = await BusinessProfile.get_or_create(session)
    if subject_template is not None:
        profile.email_subject_template = subject_template or None
    if body_template is not None:
        profile.email_body_template = body_template or None
    await session.commit()
    await session.refresh(profile)
    return email_templates(profile)


async def preview_invoice_email(
    session: AsyncSession,
    invoice_id: int,
    subject_template: str | None = None,
    body_template: str | None = None,
) -> dict | None:
    """Expand the given (or stored, or default) templates for an invoice; None if missing."""
    EmailTemplatesUpdate(email_subject_template=subject_template, email_body_template=body_template)
    invoice = await InvoiceService.get_invoice(session, invoice_id)
    if not invoice:
        return None

    profile = await BusinessProfile.get_or_create(session)
    if subject_template is None:
        subject_template = profile.email_subject_template or DEFAULT_SUBJECT_TEMPLATE
    if body_template is None:
        body_template = profile.email_body_template or DEFAULT_BODY_TEMPLATE

    return {
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "recipient_email": invoice.client_email,
        "subject": expand_template(subject_template, invoice, profile),
        "body": expand_template(body_template, invoice, profile),
        "subject_template_used": subject_template,
        "body_template_used": body_template,
    }
