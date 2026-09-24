"""Email templates API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import BusinessProfile, get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.service import email as email_service
from invoice_machine.service.profile import EmailTemplatesUpdate

router = APIRouter(tags=["email-templates"])


class EmailTemplatesSchema(BaseModel):
    """Email templates response."""

    email_subject_template: str | None = None
    email_body_template: str | None = None
    available_placeholders: list[str]
    default_subject: str
    default_body: str


class EmailPreviewRequest(BaseModel):
    """Request to preview email for an invoice."""

    subject_template: str | None = Field(None, max_length=500)
    body_template: str | None = Field(None, max_length=10000)


class EmailPreviewResponse(BaseModel):
    """Expanded email preview response."""

    invoice_id: int
    invoice_number: str
    recipient_email: str | None
    subject: str
    body: str
    subject_template_used: str
    body_template_used: str


@router.get("/api/settings/email-templates")
@limiter.limit("60/minute")
async def get_email_templates(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> EmailTemplatesSchema:
    """Get email templates and available placeholders."""
    profile = await BusinessProfile.get_or_create(session)
    return EmailTemplatesSchema.model_validate(email_service.email_templates(profile))


@router.put("/api/settings/email-templates")
@limiter.limit("30/hour")
async def update_email_templates(
    request: Request,
    data: EmailTemplatesUpdate,
    session: AsyncSession = Depends(get_session),
) -> EmailTemplatesSchema:
    """Update email templates."""
    templates = await email_service.update_email_templates(
        session, data.email_subject_template, data.email_body_template
    )
    return EmailTemplatesSchema.model_validate(templates)


@router.post("/api/invoices/{invoice_id}/email-preview")
@limiter.limit("60/minute")
async def preview_invoice_email(
    request: Request,
    invoice_id: int,
    data: EmailPreviewRequest,
    session: AsyncSession = Depends(get_session),
) -> EmailPreviewResponse:
    """Preview email content for an invoice with template expansion."""
    preview = await email_service.preview_invoice_email(
        session, invoice_id, data.subject_template, data.body_template
    )
    if preview is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return EmailPreviewResponse.model_validate(preview)
