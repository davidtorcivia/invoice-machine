"""Analytics API endpoints.

Optimized for performance using SQL-level aggregation instead of in-memory loops.
This is critical for scaling to thousands of invoices.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case, and_, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import get_session, Invoice
from invoice_machine.services import ClientService, format_currency
from invoice_machine.rate_limit import limiter
from starlette.requests import Request

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Reasonable limits to prevent excessive queries
MAX_INVOICE_QUERY_LIMIT = 1000
MAX_CLIENT_LIMIT = 100


@router.get("/revenue")
@limiter.limit("30/minute")
async def get_revenue_summary(
    request: Request,
    from_date: Optional[str] = Query(
        None, description="Start date (ISO format, defaults to start of current year)"
    ),
    to_date: Optional[str] = Query(
        None, description="End date (ISO format, defaults to today)"
    ),
    group_by: str = Query(
        "month", pattern="^(month|quarter|year)$", description="How to group breakdown"
    ),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Get revenue summary for the specified period.

    Returns total invoiced, paid, outstanding, and breakdown by period.

    Uses SQL-level aggregation for O(1) memory usage regardless of invoice count.
    """
    today = date.today()
    from_date_parsed = date.fromisoformat(from_date) if from_date else date(today.year, 1, 1)
    to_date_parsed = date.fromisoformat(to_date) if to_date else today

    # Base filter for date range and non-deleted invoices
    base_filter = and_(
        Invoice.issue_date >= from_date_parsed,
        Invoice.issue_date <= to_date_parsed,
        Invoice.deleted_at.is_(None),
    )

    # SQL aggregation query - single pass through the data
    totals_query = select(
        func.count(Invoice.id).label("invoice_count"),
        func.coalesce(func.sum(Invoice.total), 0).label("total_invoiced"),
        func.coalesce(
            func.sum(case((Invoice.status == "paid", Invoice.total), else_=0)), 0
        ).label("total_paid"),
        func.coalesce(
            func.sum(
                case((Invoice.status.in_(["sent", "overdue"]), Invoice.total), else_=0)
            ),
            0,
        ).label("total_outstanding"),
        func.coalesce(
            func.sum(case((Invoice.status == "draft", Invoice.total), else_=0)), 0
        ).label("total_draft"),
        func.coalesce(
            func.sum(case((Invoice.status == "overdue", Invoice.total), else_=0)), 0
        ).label("total_overdue"),
    ).where(base_filter)

    result = await session.execute(totals_query)
    totals = result.one()

    invoice_count = totals.invoice_count
    total_invoiced = Decimal(str(totals.total_invoiced))
    total_paid = Decimal(str(totals.total_paid))
    total_outstanding = Decimal(str(totals.total_outstanding))
    total_draft = Decimal(str(totals.total_draft))
    total_overdue = Decimal(str(totals.total_overdue))

    # Period breakdown query using SQL grouping
    # SQLite uses strftime for date formatting
    if group_by == "month":
        period_expr = func.strftime("%Y-%m", Invoice.issue_date)
    elif group_by == "quarter":
        # SQLite doesn't have a built-in quarter function, compute manually
        # Q = ((month - 1) / 3) + 1
        period_expr = func.printf(
            "%d-Q%d",
            func.cast(func.strftime("%Y", Invoice.issue_date), Integer),
            (func.cast(func.strftime("%m", Invoice.issue_date), Integer) - 1) / 3 + 1,
        )
    else:  # year
        period_expr = func.strftime("%Y", Invoice.issue_date)

    breakdown_query = (
        select(
            period_expr.label("period"),
            func.count(Invoice.id).label("count"),
            func.coalesce(func.sum(Invoice.total), 0).label("invoiced"),
            func.coalesce(
                func.sum(case((Invoice.status == "paid", Invoice.total), else_=0)), 0
            ).label("paid"),
        )
        .where(base_filter)
        .group_by(period_expr)
        .order_by(period_expr)
    )

    breakdown_result = await session.execute(breakdown_query)
    breakdown_rows = breakdown_result.all()

    breakdown = [
        {
            "period": row.period,
            "invoiced": str(Decimal(str(row.invoiced))),
            "invoiced_formatted": format_currency(Decimal(str(row.invoiced)), "USD"),
            "paid": str(Decimal(str(row.paid))),
            "paid_formatted": format_currency(Decimal(str(row.paid)), "USD"),
            "count": row.count,
        }
        for row in breakdown_rows
    ]

    return {
        "period": f"{from_date_parsed} to {to_date_parsed}",
        "totals": {
            "invoiced": str(total_invoiced),
            "invoiced_formatted": format_currency(total_invoiced, "USD"),
            "paid": str(total_paid),
            "paid_formatted": format_currency(total_paid, "USD"),
            "outstanding": str(total_outstanding),
            "outstanding_formatted": format_currency(total_outstanding, "USD"),
            "draft": str(total_draft),
            "draft_formatted": format_currency(total_draft, "USD"),
            "overdue": str(total_overdue),
            "overdue_formatted": format_currency(total_overdue, "USD"),
            "invoice_count": invoice_count,
        },
        "breakdown": breakdown,
    }


@router.get("/clients")
@limiter.limit("30/minute")
async def get_client_lifetime_values(
    request: Request,
    client_id: Optional[int] = Query(None, description="Specific client ID"),
    limit: int = Query(20, ge=1, le=100, description="Max clients to return"),
    session: AsyncSession = Depends(get_session),
) -> list:
    """
    Get lifetime value for clients.

    Returns list of clients with total invoiced, paid, and invoice counts.
    Sorted by total paid descending.

    Uses optimized SQL aggregation to avoid N+1 queries.
    """
    # Use optimized aggregated query instead of N+1 individual queries
    stats = await ClientService.get_client_invoice_stats(
        session,
        client_id=client_id,
        limit=min(limit, MAX_CLIENT_LIMIT),
    )

    # Format results
    results = [
        {
            "client_id": stat["client_id"],
            "name": stat["name"],
            "email": stat["email"],
            "total_invoiced": str(stat["total_invoiced"]),
            "total_invoiced_formatted": format_currency(stat["total_invoiced"], "USD"),
            "total_paid": str(stat["total_paid"]),
            "total_paid_formatted": format_currency(stat["total_paid"], "USD"),
            "invoice_count": stat["invoice_count"],
            "paid_invoice_count": stat["paid_invoice_count"],
            "first_invoice": stat["first_invoice"].isoformat() if stat["first_invoice"] else None,
            "last_invoice": stat["last_invoice"].isoformat() if stat["last_invoice"] else None,
        }
        for stat in stats
    ]

    # Sort by total paid (descending)
    results.sort(key=lambda x: Decimal(x["total_paid"]), reverse=True)
    return results
