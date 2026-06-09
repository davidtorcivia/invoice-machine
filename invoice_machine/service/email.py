"""Shared invoice-email orchestration used by both the REST API and MCP tools.

Centralizes the "send an invoice by email" flow so the two surfaces cannot drift:
SMTP-enabled check, PDF freshness, delivery, and the draft -> sent transition all
live here. Heavy imports are deferred to call time to avoid an import cycle
(email.py imports invoice_machine.services).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import BusinessProfile
from invoice_machine.utils import utc_now


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
    successful send moves a draft to ``sent`` (recorded as ``status_updated``).
    """
    from invoice_machine.email import EmailService
    from invoice_machine.pdf.generator import generate_pdf
    from invoice_machine.services import InvoiceService

    profile = await BusinessProfile.get_or_create(session)
    if not profile.smtp_enabled:
        return {
            "success": False,
            "error": "SMTP is not enabled. Configure SMTP settings first.",
        }

    invoice = await InvoiceService.get_invoice(session, invoice_id)
    if not invoice:
        return {"success": False, "error": f"Invoice {invoice_id} not found", "not_found": True}

    # Never email a stale or missing PDF.
    if not invoice.pdf_path or invoice.needs_pdf_regeneration:
        invoice.pdf_path = await generate_pdf(session, invoice)
        invoice.pdf_generated_at = utc_now()
        await session.commit()

    email_service = EmailService(profile)
    result = await email_service.send_invoice(
        invoice,
        recipient_email=recipient_email,
        subject=subject,
        body=body,
    )

    if result.get("success") and invoice.status == "draft":
        invoice.status = "sent"
        await session.commit()
        result["status_updated"] = "sent"

    return result
