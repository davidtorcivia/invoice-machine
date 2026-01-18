"""Search API endpoints."""

from fastapi import APIRouter, Depends, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from invoicely.database import get_session
from invoicely.services import SearchService

router = APIRouter(prefix="/api/search", tags=["search"])
limiter = Limiter(key_func=get_remote_address)


@router.get("")
@limiter.limit("60/minute")
async def search(
    request: Request,
    q: str = Query("", max_length=200, description="Search query"),
    invoices: bool = Query(True, description="Include invoices in search"),
    clients: bool = Query(True, description="Include clients in search"),
    limit: int = Query(20, ge=1, le=100, description="Max results per category"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Search across invoices and clients.

    Uses full-text search (FTS5) for fast matching.
    Returns matching invoices and clients with relevance ranking.
    Empty query returns empty results.
    """
    # Return empty results for empty/whitespace queries
    if not q or not q.strip():
        return {"invoices": [], "clients": []}

    results = await SearchService.search(
        session,
        query=q,
        search_invoices=invoices,
        search_clients=clients,
        limit=limit,
    )
    return results
