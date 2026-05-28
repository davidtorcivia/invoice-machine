"""Analytics API endpoints.

Thin HTTP layer over invoice_machine.service.analytics, which performs
currency-aware SQL aggregation. The MCP tools call the same service so the two
surfaces cannot diverge.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from invoice_machine.database import get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.service import analytics as analytics_service
from invoice_machine.utils import utc_now

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Reasonable limits to prevent excessive queries
MAX_CLIENT_LIMIT = 100


@router.get("/dashboard")
@limiter.limit("30/minute")
async def get_dashboard_summary(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get dashboard summary totals for invoice documents."""
    return await analytics_service.dashboard_summary(session)


@router.get("/revenue")
@limiter.limit("30/minute")
async def get_revenue_summary(
    request: Request,
    from_date: str | None = Query(
        None, description="Start date (ISO format, defaults to start of current year)"
    ),
    to_date: str | None = Query(None, description="End date (ISO format, defaults to today)"),
    group_by: str = Query(
        "month", pattern="^(month|quarter|year)$", description="How to group breakdown"
    ),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get revenue summary for the specified period (grouped by currency)."""
    today = utc_now().date()
    from_date_parsed = date.fromisoformat(from_date) if from_date else date(today.year, 1, 1)
    to_date_parsed = date.fromisoformat(to_date) if to_date else today
    return await analytics_service.revenue_summary(
        session, from_date_parsed, to_date_parsed, group_by
    )


@router.get("/clients")
@limiter.limit("30/minute")
async def get_client_lifetime_values(
    request: Request,
    client_id: int | None = Query(None, description="Specific client ID"),
    limit: int = Query(20, ge=1, le=100, description="Max clients to return"),
    session: AsyncSession = Depends(get_session),
) -> list:
    """Get lifetime value for clients (in each client's dominant currency)."""
    return await analytics_service.client_lifetime_values(
        session, client_id=client_id, limit=min(limit, MAX_CLIENT_LIMIT)
    )
