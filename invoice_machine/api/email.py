"""Email/SMTP API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from invoice_machine.database import get_session, BusinessProfile
from invoice_machine.services import InvoiceService
from invoice_machine.email import EmailService
from invoice_machine.crypto import encrypt_credential
from invoice_machine.rate_limit import limiter

router = APIRouter(tags=["email"])


class SMTPSettingsSchema(BaseModel):
    """SMTP settings response (password masked)."""

    smtp_enabled: bool
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password_set: bool = False  # Never expose actual password
    smtp_from_email: Optional[str] = None
    smtp_from_name: Optional[str] = None
    smtp_use_tls: bool = True


class SMTPSettingsUpdate(BaseModel):
    """SMTP settings update request."""

    smtp_enabled: Optional[bool] = None
    smtp_host: Optional[str] = Field(None, max_length=255)
    smtp_port: Optional[int] = Field(None, ge=1, le=65535)
    smtp_username: Optional[str] = Field(None, max_length=255)
    smtp_password: Optional[str] = Field(None, max_length=255)
    smtp_from_email: Optional[str] = Field(None, max_length=255)
    smtp_from_name: Optional[str] = Field(None, max_length=255)
    smtp_use_tls: Optional[bool] = None


class SendEmailRequest(BaseModel):
    """Send invoice email request."""

    recipient_email: Optional[str] = Field(None, max_length=255)
    subject: Optional[str] = Field(None, max_length=500)
    body: Optional[str] = Field(None, max_length=10000)


def _profile_to_smtp_settings(profile: BusinessProfile) -> dict:
    """Convert profile to SMTP settings response."""
    return {
        "smtp_enabled": bool(profile.smtp_enabled),
        "smtp_host": profile.smtp_host,
        "smtp_port": profile.smtp_port or 587,
        "smtp_username": profile.smtp_username,
        "smtp_password_set": bool(profile.smtp_password),
        "smtp_from_email": profile.smtp_from_email,
        "smtp_from_name": profile.smtp_from_name,
        "smtp_use_tls": bool(profile.smtp_use_tls) if profile.smtp_use_tls is not None else True,
    }


@router.get("/api/settings/smtp")
async def get_smtp_settings(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get SMTP settings (password is masked)."""
    profile = await BusinessProfile.get_or_create(session)
    return _profile_to_smtp_settings(profile)


@router.put("/api/settings/smtp")
async def update_smtp_settings(
    data: SMTPSettingsUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update SMTP settings."""
    profile = await BusinessProfile.get_or_create(session)

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)

    # Convert booleans to integers for SQLite
    if "smtp_enabled" in update_data:
        update_data["smtp_enabled"] = int(update_data["smtp_enabled"])
    if "smtp_use_tls" in update_data:
        update_data["smtp_use_tls"] = int(update_data["smtp_use_tls"])

    # Encrypt SMTP password before storage
    if "smtp_password" in update_data and update_data["smtp_password"]:
        update_data["smtp_password"] = encrypt_credential(update_data["smtp_password"])

    for key, value in update_data.items():
        setattr(profile, key, value)

    await session.commit()
    await session.refresh(profile)

    return _profile_to_smtp_settings(profile)


@router.post("/api/settings/smtp/test")
@limiter.limit("5/minute")  # Limit connection tests to prevent abuse
async def test_smtp_connection(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Test SMTP connection."""
    profile = await BusinessProfile.get_or_create(session)
    email_service = EmailService(profile)

    result = await email_service.test_connection()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Connection failed"))

    return result


@router.post("/api/invoices/{invoice_id}/send-email")
@limiter.limit("10/minute")  # Limit email sending to prevent spam abuse
async def send_invoice_email(
    request: Request,
    invoice_id: int,
    data: SendEmailRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Send invoice via email."""
    # Get invoice
    invoice = await InvoiceService.get_invoice(session, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Get profile for SMTP settings
    profile = await BusinessProfile.get_or_create(session)

    if not profile.smtp_enabled:
        raise HTTPException(
            status_code=400, detail="SMTP is not enabled. Configure SMTP settings first."
        )

    # Check PDF exists
    if not invoice.pdf_path:
        raise HTTPException(
            status_code=400, detail="Invoice PDF not generated. Generate PDF first."
        )

    # Send email
    email_service = EmailService(profile)
    result = await email_service.send_invoice(
        invoice,
        recipient_email=data.recipient_email,
        subject=data.subject,
        body=data.body,
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to send email"))

    return result
