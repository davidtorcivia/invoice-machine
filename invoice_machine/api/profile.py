"""Business profile API endpoints."""

import logging
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.config import get_settings
from invoice_machine.database import BusinessProfile, get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.service.profile import BusinessProfileUpdate, apply_profile_updates
from invoice_machine.utils import confined_file, detect_image_type, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/profile", tags=["profile"])
settings = get_settings()


class BusinessProfileSchema(BaseModel):
    """Business profile schema."""

    id: int
    name: str
    business_name: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str = "United States"
    email: str | None = None
    phone: str | None = None
    ein: str | None = None
    logo_path: str | None = None
    accent_color: str = "#16a34a"
    default_payment_terms_days: int = 30
    default_currency_code: str = "USD"
    default_notes: str | None = None
    default_payment_instructions: str | None = None
    payment_methods: str | None = None  # JSON string: [{id, name, instructions}]
    theme_preference: str = "system"
    app_base_url: str | None = None  # App base URL for links
    # Tax settings
    default_tax_enabled: bool = False
    default_tax_rate: str | None = None
    default_tax_name: str = "Tax"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("default_tax_rate", mode="before")
    @classmethod
    def convert_tax_rate(cls, v):
        """Convert Decimal tax rate to string."""
        if v is not None:
            return str(v)
        return v


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal."""
    name = os.path.basename(filename)
    name = "".join(c for c in name if c.isalnum() or c in "._-")
    return name


def _delete_logo_file(logo_filename: str | None) -> None:
    """Best-effort removal of a logo file from the logo directory."""
    if not logo_filename:
        return
    safe_name = sanitize_filename(logo_filename)
    if not safe_name:
        return
    logo_file = confined_file(settings.logo_dir, safe_name)
    if logo_file is None:
        return
    try:
        logo_file.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not delete logo file %s: %s", safe_name, exc)


def detect_image_extension(content: bytes) -> str | None:
    """Return the file extension implied by the content's magic bytes.

    The stored extension is derived from the bytes, never from the client-supplied
    filename, so a PNG uploaded as "logo.jpg" is stored (and later served) as the
    format it actually is.
    """
    detected = detect_image_type(content)
    return detected[0] if detected else None


@router.get("", response_model=BusinessProfileSchema)
@limiter.limit("120/minute")
async def get_profile(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> BusinessProfile:
    """Get business profile."""
    profile = await BusinessProfile.get_or_create(session)
    return profile


@router.put("", response_model=BusinessProfileSchema)
@limiter.limit("30/hour")
async def update_profile(
    request: Request,
    updates: BusinessProfileUpdate,
    session: AsyncSession = Depends(get_session),
) -> BusinessProfile:
    """Update business profile."""
    profile = await BusinessProfile.get_or_create(session)
    apply_profile_updates(profile, updates.model_dump(exclude_unset=True))
    profile.updated_at = utc_now()
    await session.commit()
    await session.refresh(profile)

    return profile


@router.post("/logo")
@limiter.limit("10/minute")
async def upload_logo(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """Upload business logo."""
    from pathlib import Path

    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    filename = sanitize_filename(file.filename)
    ext = Path(filename).suffix.lower()

    if ext.lower() not in settings.allowed_logo_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(settings.allowed_logo_extensions)}",
        )

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # Read in chunks so oversized uploads do not have to be buffered fully in memory.
    max_bytes = settings.max_logo_size_mb * 1024 * 1024
    buffer = bytearray()
    while chunk := await file.read(1024 * 1024):
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {settings.max_logo_size_mb}MB",
            )
    contents = bytes(buffer)

    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # The extension comes from the content's magic bytes, never from the
    # client-supplied filename.
    detected_ext = detect_image_extension(contents)
    if detected_ext is None:
        raise HTTPException(status_code=400, detail="File does not appear to be a valid image")

    unique_filename = f"logo-{uuid.uuid4().hex}{detected_ext}"

    settings.logo_dir.mkdir(parents=True, exist_ok=True)

    path = confined_file(settings.logo_dir, unique_filename)
    if path is None:
        raise HTTPException(status_code=400, detail="Invalid file path")

    path.write_bytes(contents)

    profile = await BusinessProfile.get_or_create(session)
    previous_logo = profile.logo_path
    profile.logo_path = unique_filename
    profile.updated_at = utc_now()
    await session.commit()

    # Only after the new logo is committed: drop the superseded file so repeated
    # uploads don't accumulate orphans in the logo directory forever.
    if previous_logo and previous_logo != unique_filename:
        _delete_logo_file(previous_logo)

    return {"logo_path": unique_filename, "url": f"/api/profile/logo/{unique_filename}"}


@router.delete("/logo")
@limiter.limit("10/hour")
async def delete_logo(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Delete business logo."""
    profile = await BusinessProfile.get_or_create(session)

    if profile.logo_path:
        previous_logo = profile.logo_path
        profile.logo_path = None
        profile.updated_at = utc_now()
        await session.commit()
        _delete_logo_file(previous_logo)

    return {"success": True}


@router.get("/logo/{filename:path}")
@limiter.limit("120/minute")
async def get_logo(request: Request, filename: str):
    """Serve uploaded logo."""
    safe_filename = sanitize_filename(filename)

    settings.logo_dir.mkdir(parents=True, exist_ok=True)

    resolved_path = confined_file(settings.logo_dir, safe_filename)
    if resolved_path is None or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Logo not found")

    return FileResponse(resolved_path)
