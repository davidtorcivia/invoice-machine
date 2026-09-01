"""Labeled API key management (web session only - see auth_middleware)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.crypto import generate_api_key, hash_api_key
from invoice_machine.database import ApiKey, get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.utils import utc_now

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])

SHOWN_ONCE_WARNING = "This key is only shown once. Save it now - it cannot be recovered."


class ApiKeyRename(BaseModel):
    """Request body for relabeling a key."""

    label: str = Field(min_length=1, max_length=100)

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("label must not be empty")
        return stripped


class ApiKeyCreate(ApiKeyRename):
    """Request body for minting a key."""

    kind: Literal["mcp", "bot"]


def _record(key: ApiKey) -> dict:
    return {
        "id": key.id,
        "kind": key.kind,
        "label": key.label,
        "prefix": key.prefix,
        "created_at": key.created_at.isoformat() if key.created_at else None,
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
    }


async def _get_or_404(session: AsyncSession, key_id: int) -> ApiKey:
    key = await session.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    return key


@router.get("")
async def list_api_keys(session: AsyncSession = Depends(get_session)):
    """List every key, without any secret material."""
    result = await session.execute(select(ApiKey).order_by(ApiKey.kind, ApiKey.created_at))
    return [_record(key) for key in result.scalars()]


@router.post("", status_code=201)
@limiter.limit("10/hour")
async def create_api_key(
    request: Request,
    payload: ApiKeyCreate,
    session: AsyncSession = Depends(get_session),
):
    """Mint a key. The plaintext is returned here and never again."""
    plain_key = generate_api_key(payload.kind)
    key = ApiKey(
        kind=payload.kind,
        label=payload.label,
        key_hash=hash_api_key(plain_key),
        prefix=plain_key[:12],
        created_at=utc_now(),
    )
    session.add(key)
    await session.commit()
    await session.refresh(key)

    return {**_record(key), "key": plain_key, "warning": SHOWN_ONCE_WARNING}


@router.patch("/{key_id}")
async def rename_api_key(
    key_id: int,
    payload: ApiKeyRename,
    session: AsyncSession = Depends(get_session),
):
    """Change a key's label."""
    key = await _get_or_404(session, key_id)
    key.label = payload.label
    await session.commit()
    await session.refresh(key)
    return _record(key)


@router.post("/{key_id}/rotate")
@limiter.limit("10/hour")
async def rotate_api_key(
    request: Request,
    key_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Replace a key's secret in place, keeping its id and label."""
    key = await _get_or_404(session, key_id)
    plain_key = generate_api_key(key.kind)
    key.key_hash = hash_api_key(plain_key)
    key.prefix = plain_key[:12]
    key.created_at = utc_now()
    key.last_used_at = None
    await session.commit()
    await session.refresh(key)

    return {**_record(key), "key": plain_key, "warning": SHOWN_ONCE_WARNING}


@router.delete("/{key_id}")
async def delete_api_key(
    key_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Revoke a key immediately."""
    key = await _get_or_404(session, key_id)
    await session.delete(key)
    await session.commit()
    return {"success": True}
