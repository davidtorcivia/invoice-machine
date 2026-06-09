"""Business profile API endpoints."""

import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.config import get_settings
from invoice_machine.database import BusinessProfile, get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.utils import utc_now

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
    mcp_api_key_configured: bool = False
    bot_api_key_configured: bool = False
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


class BusinessProfileUpdate(BaseModel):
    """Business profile update schema."""

    name: str | None = Field(None, max_length=255)
    business_name: str | None = Field(None, max_length=255)
    address_line1: str | None = Field(None, max_length=500)
    address_line2: str | None = Field(None, max_length=500)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    country: str | None = Field(None, max_length=100)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    ein: str | None = Field(None, max_length=50)
    accent_color: str | None = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    default_payment_terms_days: int | None = Field(None, ge=0, le=365)
    default_currency_code: str | None = Field(None, pattern="^[A-Z]{3}$")
    default_notes: str | None = Field(None, max_length=10000)
    default_payment_instructions: str | None = Field(None, max_length=10000)
    payment_methods: str | None = Field(None, max_length=10000)  # JSON string
    theme_preference: str | None = Field(None, pattern="^(system|light|dark)$")
    app_base_url: str | None = Field(None, max_length=500)
    # Tax settings
    default_tax_enabled: bool | None = None
    default_tax_rate: str | None = Field(None, max_length=10)
    default_tax_name: str | None = Field(None, max_length=50)


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal."""
    # Remove any directory components
    name = os.path.basename(filename)
    # Remove any non-alphanumeric chars except dots, dashes, underscores
    name = "".join(c for c in name if c.isalnum() or c in "._-")
    return name


# Image magic bytes for validation
# Note: SVG is excluded due to XSS security risks (can contain embedded JavaScript)
# WebP is intentionally absent here: a bare ``RIFF`` prefix also matches AVI/WAV
# containers, so it is validated separately by its full RIFF....WEBP signature.
IMAGE_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": "png",        # PNG
    b"\xff\xd8\xff": "jpeg",             # JPEG
    b"GIF87a": "gif",                    # GIF87a
    b"GIF89a": "gif",                    # GIF89a
}


def validate_image_content(content: bytes) -> bool:
    """
    Validate that file content appears to be an image.

    Checks magic bytes to verify file is actually an image,
    not just a renamed malicious file.
    """
    if len(content) < 8:
        return False

    # Check against known image signatures
    for signature, _ in IMAGE_SIGNATURES.items():
        if content[:len(signature)] == signature:
            return True

    # WebP requires the full RIFF....WEBP container, not just a RIFF prefix.
    if content[:4] == b"RIFF" and len(content) >= 12 and content[8:12] == b"WEBP":
        return True

    return False


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

    update_data = updates.model_dump(exclude_unset=True)

    # Convert boolean to int for SQLite
    if "default_tax_enabled" in update_data and update_data["default_tax_enabled"] is not None:
        update_data["default_tax_enabled"] = int(update_data["default_tax_enabled"])

    for key, value in update_data.items():
        if value is not None:
            setattr(profile, key, value)

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

    # Check file was provided
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Validate file extension
    filename = sanitize_filename(file.filename)
    ext = Path(filename).suffix.lower()

    if ext.lower() not in settings.allowed_logo_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(settings.allowed_logo_extensions)}"
        )

    # Validate file type (content-type header check + basic validation)
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
                detail=f"File too large. Maximum size: {settings.max_logo_size_mb}MB"
            )
    contents = bytes(buffer)

    # Validate file size is not zero
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Validate file content is actually an image (magic bytes check)
    if not validate_image_content(contents):
        raise HTTPException(
            status_code=400,
            detail="File does not appear to be a valid image"
        )

    # Generate safe filename with UUID
    safe_ext = ext if ext else ".png"
    unique_filename = f"logo-{uuid.uuid4().hex}{safe_ext}"

    # Ensure logo directory exists
    settings.logo_dir.mkdir(parents=True, exist_ok=True)

    path = settings.logo_dir / unique_filename

    # Ensure path is within logo directory (defense in depth)
    if not str(path.resolve()).startswith(str(settings.logo_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid file path")

    # Save file
    path.write_bytes(contents)

    # Update profile
    profile = await BusinessProfile.get_or_create(session)
    profile.logo_path = unique_filename
    profile.updated_at = utc_now()
    await session.commit()

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
        # Try to delete the file
        logo_file = settings.logo_dir / profile.logo_path
        if logo_file.exists():
            try:
                logo_file.unlink()
            except OSError as e:
                import logging
                logging.getLogger(__name__).warning(f"Could not delete logo file: {e}")

        profile.logo_path = None
        profile.updated_at = utc_now()
        await session.commit()

    return {"success": True}


@router.get("/logo/{filename:path}")
async def get_logo(filename: str):
    """Serve uploaded logo."""
    # Sanitize filename to prevent path traversal
    safe_filename = sanitize_filename(filename)

    # Ensure logo directory exists
    settings.logo_dir.mkdir(parents=True, exist_ok=True)

    path = settings.logo_dir / safe_filename

    # Ensure resolved path is within logo directory
    resolved_path = path.resolve()
    if not str(resolved_path).startswith(str(settings.logo_dir.resolve())):
        raise HTTPException(status_code=404, detail="Logo not found")

    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail="Logo not found")

    return FileResponse(resolved_path)


@router.post("/mcp-key")
@limiter.limit("5/hour")
async def generate_mcp_key(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Generate a new MCP API key.

    IMPORTANT: The plain-text key is only shown once. It is stored hashed
    in the database and cannot be recovered. Save it immediately.
    """
    from invoice_machine.crypto import generate_api_key, hash_api_key

    profile = await BusinessProfile.get_or_create(session)

    # Generate a new random API key
    plain_key = generate_api_key()

    # Hash it before storing - the plain key is only shown once
    profile.mcp_api_key = hash_api_key(plain_key)
    profile.updated_at = utc_now()
    await session.commit()

    return {
        "mcp_api_key": plain_key,
        "warning": "This key is only shown once. Save it now - it cannot be recovered.",
    }


@router.delete("/mcp-key")
@limiter.limit("5/hour")
async def delete_mcp_key(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Delete MCP API key (disables remote MCP access)."""
    profile = await BusinessProfile.get_or_create(session)
    profile.mcp_api_key = None
    profile.updated_at = utc_now()
    await session.commit()

    return {"success": True}


@router.post("/bot-key")
@limiter.limit("5/hour")
async def generate_bot_key(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Generate a new bot API key for conventional REST API automation."""
    from invoice_machine.crypto import generate_api_key, hash_api_key

    profile = await BusinessProfile.get_or_create(session)

    plain_key = generate_api_key()
    profile.bot_api_key = hash_api_key(plain_key)
    profile.updated_at = utc_now()
    await session.commit()

    return {
        "bot_api_key": plain_key,
        "warning": "This key is only shown once. Save it now - it cannot be recovered.",
    }


@router.delete("/bot-key")
@limiter.limit("5/hour")
async def delete_bot_key(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Delete bot API key (disables bearer token REST API access)."""
    profile = await BusinessProfile.get_or_create(session)
    profile.bot_api_key = None
    profile.updated_at = utc_now()
    await session.commit()

    return {"success": True}
