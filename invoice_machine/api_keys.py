"""Lookup and verification for labeled API keys."""

import logging

from sqlalchemy import func, select

import invoice_machine.database as db
from invoice_machine.crypto import verify_api_key
from invoice_machine.utils import ensure_utc, utc_now

logger = logging.getLogger(__name__)

# Only touch the database when the recorded time is this stale, so a busy
# integration does not cause one write per request.
LAST_USED_REFRESH_SECONDS = 60


async def authenticate_api_key(kind: str, token: str) -> bool:
    """Whether the token matches any stored key of this kind."""
    if not token:
        return False

    # ponytail: linear scan per auth; unsalted sha256 unique-index lookup if key counts grow
    async with db.async_session_maker() as session:
        rows = (await session.execute(select(db.ApiKey).where(db.ApiKey.kind == kind))).scalars()
        for row in rows:
            if not verify_api_key(token, row.key_hash):
                continue
            now = utc_now()
            last_used = ensure_utc(row.last_used_at)
            if last_used is None or (now - last_used).total_seconds() > LAST_USED_REFRESH_SECONDS:
                row.last_used_at = now
                try:
                    await session.commit()
                except Exception:
                    # Bookkeeping only: a valid key must still authenticate.
                    logger.warning("Failed to record API key last_used_at", exc_info=True)
            return True
    return False


async def count_api_keys(kind: str) -> int:
    """Number of stored keys of this kind."""
    async with db.async_session_maker() as session:
        result = await session.execute(
            select(func.count()).select_from(db.ApiKey).where(db.ApiKey.kind == kind)
        )
        return result.scalar_one()
