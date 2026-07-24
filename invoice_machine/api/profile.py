"""Business profile API endpoints."""

import json
import logging
import os
import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.config import get_settings
from invoice_machine.database import BusinessProfile, get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.utils import utc_now

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
    # Tax settings. Decimal with bounds, not a free-form string: "abc" used to
    # reach the DECIMAL column and 500, and "999" was accepted verbatim as a
    # 999% default rate applied to every subsequently created invoice.
    default_tax_enabled: bool | None = None
    default_tax_rate: Decimal | None = Field(None, ge=0, le=100)
    default_tax_name: str | None = Field(None, max_length=50)

    @field_validator("payment_methods")
    @classmethod
    def validate_payment_methods(cls, value: str | None) -> str | None:
        """Reject payment_methods that isn't a JSON array of {id, name, instructions}.

        Unparseable JSON was stored happily and then silently degraded to an empty
        list everywhere it was read, so a user's payment methods just disappeared.
        """
        if value is None or value == "":
            return value
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("payment_methods must be valid JSON") from None
        if not isinstance(parsed, list):
            raise ValueError("payment_methods must be a JSON array")
        if len(parsed) > 50:
            raise ValueError("payment_methods supports at most 50 entries")
        for entry in parsed:
            if not isinstance(entry, dict):
                raise ValueError("each payment method must be a JSON object")
            if not str(entry.get("id") or "").strip():
                raise ValueError("each payment method needs a non-empty id")
            if not str(entry.get("name") or "").strip():
                raise ValueError("each payment method needs a non-empty name")
        return value


# Optional profile columns that an explicit `null` may legitimately clear. Every
# other column is NOT NULL (or has app-level meaning for its default), so a null
# there is treated as "leave unchanged".
NULLABLE_PROFILE_FIELDS = frozenset(
    {
        "business_name",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "postal_code",
        "email",
        "phone",
        "ein",
        "default_notes",
        "default_payment_instructions",
        "payment_methods",
        "app_base_url",
    }
)


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal."""
    # Remove any directory components
    name = os.path.basename(filename)
    # Remove any non-alphanumeric chars except dots, dashes, underscores
    name = "".join(c for c in name if c.isalnum() or c in "._-")
    return name


def _delete_logo_file(logo_filename: str | None) -> None:
    """Best-effort removal of a logo file from the logo directory."""
    if not logo_filename:
        return
    safe_name = sanitize_filename(logo_filename)
    if not safe_name:
        return
    logo_file = settings.logo_dir / safe_name
    try:
        if logo_file.resolve().parent != settings.logo_dir.resolve():
            return
        logo_file.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not delete logo file %s: %s", safe_name, exc)


# Image magic bytes for validation
# Note: SVG is excluded due to XSS security risks (can contain embedded JavaScript)
# WebP is intentionally absent here: a bare ``RIFF`` prefix also matches AVI/WAV
# containers, so it is validated separately by its full RIFF....WEBP signature.
IMAGE_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": ".png",        # PNG
    b"\xff\xd8\xff": ".jpg",             # JPEG
    b"GIF87a": ".gif",                   # GIF87a
    b"GIF89a": ".gif",                   # GIF89a
}


def detect_image_extension(content: bytes) -> str | None:
    """Return the file extension implied by the content's magic bytes.

    The stored extension is derived from the bytes, never from the client-supplied
    filename, so a PNG uploaded as "logo.jpg" is stored (and later served) as the
    format it actually is.
    """
    if len(content) < 8:
        return None

    for signature, extension in IMAGE_SIGNATURES.items():
        if content[: len(signature)] == signature:
            return extension

    # WebP requires the full RIFF....WEBP container, not just a RIFF prefix.
    if content[:4] == b"RIFF" and len(content) >= 12 and content[8:12] == b"WEBP":
        return ".webp"

    return None


def validate_image_content(content: bytes) -> bool:
    """
    Validate that file content appears to be an image.

    Checks magic bytes to verify file is actually an image,
    not just a renamed malicious file.
    """
    return detect_image_extension(content) is not None


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
        # An explicit null clears an optional field; NOT-NULL columns keep their
        # current value rather than blowing up on an IntegrityError.
        if value is None and key not in NULLABLE_PROFILE_FIELDS:
            continue
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

    # Validate file content is actually an image (magic bytes check) and take the
    # extension from the content rather than the client-supplied filename.
    detected_ext = detect_image_extension(contents)
    if detected_ext is None:
        raise HTTPException(
            status_code=400,
            detail="File does not appear to be a valid image"
        )

    unique_filename = f"logo-{uuid.uuid4().hex}{detected_ext}"

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
