"""Email templates API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import get_session, BusinessProfile
from invoice_machine.services import InvoiceService
from invoice_machine.email import expand_template, DEFAULT_SUBJECT_TEMPLATE, DEFAULT_BODY_TEMPLATE

router = APIRouter(tags=["email-templates"])


# Available template placeholders
AVAILABLE_PLACEHOLDERS = [
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
    "{line_items}",
]


class EmailTemplatesSchema(BaseModel):
    """Email templates response."""

    email_subject_template: Optional[str] = None
    email_body_template: Optional[str] = None
    available_placeholders: list[str] = AVAILABLE_PLACEHOLDERS
    default_subject: str = DEFAULT_SUBJECT_TEMPLATE
    default_body: str = DEFAULT_BODY_TEMPLATE


class EmailTemplatesUpdate(BaseModel):
    """Update email templates request."""

    email_subject_template: Optional[str] = Field(None, max_length=500)
    email_body_template: Optional[str] = Field(None, max_length=10000)


class EmailPreviewRequest(BaseModel):
    """Request to preview email for an invoice."""

    subject_template: Optional[str] = Field(None, max_length=500)
    body_template: Optional[str] = Field(None, max_length=10000)


class EmailPreviewResponse(BaseModel):
    """Expanded email preview response."""

    invoice_id: int
    invoice_number: str
    recipient_email: Optional[str]
    subject: str
    body: str
    subject_template_used: str
    body_template_used: str


@router.get("/api/settings/email-templates")
async def get_email_templates(
    session: AsyncSession = Depends(get_session),
) -> EmailTemplatesSchema:
    """Get email templates and available placeholders."""
    profile = await BusinessProfile.get_or_create(session)
    return EmailTemplatesSchema(
        email_subject_template=profile.email_subject_template,
        email_body_template=profile.email_body_template,
    )


@router.put("/api/settings/email-templates")
async def update_email_templates(
    data: EmailTemplatesUpdate,
    session: AsyncSession = Depends(get_session),
) -> EmailTemplatesSchema:
    """Update email templates."""
    profile = await BusinessProfile.get_or_create(session)

    # Update fields - empty string clears the template (uses default)
    if data.email_subject_template is not None:
        profile.email_subject_template = data.email_subject_template or None
    if data.email_body_template is not None:
        profile.email_body_template = data.email_body_template or None

    await session.commit()
    await session.refresh(profile)

    return EmailTemplatesSchema(
        email_subject_template=profile.email_subject_template,
        email_body_template=profile.email_body_template,
    )


@router.post("/api/invoices/{invoice_id}/email-preview")
async def preview_invoice_email(
    invoice_id: int,
    data: EmailPreviewRequest,
    session: AsyncSession = Depends(get_session),
) -> EmailPreviewResponse:
    """Preview email content for an invoice with template expansion."""
    invoice = await InvoiceService.get_invoice(session, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    profile = await BusinessProfile.get_or_create(session)

    # Use provided templates, fall back to saved templates, then defaults
    subject_template = (
        data.subject_template
        if data.subject_template is not None
        else (profile.email_subject_template or DEFAULT_SUBJECT_TEMPLATE)
    )
    body_template = (
        data.body_template
        if data.body_template is not None
        else (profile.email_body_template or DEFAULT_BODY_TEMPLATE)
    )

    # Expand templates with invoice data
    subject = expand_template(subject_template, invoice, profile)
    body = expand_template(body_template, invoice, profile)

    return EmailPreviewResponse(
        invoice_id=invoice.id,
        invoice_number=invoice.invoice_number,
        recipient_email=invoice.client_email,
        subject=subject,
        body=body,
        subject_template_used=subject_template,
        body_template_used=body_template,
    )
