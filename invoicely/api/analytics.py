"""Analytics API endpoints."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from invoicely.database import get_session
from invoicely.services import InvoiceService, ClientService, format_currency
from invoicely.rate_limit import limiter
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
    """
    today = date.today()
    from_date_parsed = date.fromisoformat(from_date) if from_date else date(today.year, 1, 1)
    to_date_parsed = date.fromisoformat(to_date) if to_date else today

    # Get all invoices in range (exclude deleted)
    invoices = await InvoiceService.list_invoices(
        session,
        from_date=from_date_parsed,
        to_date=to_date_parsed,
        limit=MAX_INVOICE_QUERY_LIMIT,
    )

    # Calculate totals
    total_invoiced = sum(inv.total for inv in invoices)
    total_paid = sum(inv.total for inv in invoices if inv.status == "paid")
    total_outstanding = sum(inv.total for inv in invoices if inv.status in ("sent", "overdue"))
    total_draft = sum(inv.total for inv in invoices if inv.status == "draft")
    total_overdue = sum(inv.total for inv in invoices if inv.status == "overdue")

    # Group by period
    by_period = defaultdict(lambda: {"invoiced": Decimal(0), "paid": Decimal(0), "count": 0})

    for inv in invoices:
        if group_by == "month":
            period = inv.issue_date.strftime("%Y-%m")
        elif group_by == "quarter":
            q = (inv.issue_date.month - 1) // 3 + 1
            period = f"{inv.issue_date.year}-Q{q}"
        else:
            period = str(inv.issue_date.year)

        by_period[period]["invoiced"] += inv.total
        by_period[period]["count"] += 1
        if inv.status == "paid":
            by_period[period]["paid"] += inv.total

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
            "invoice_count": len(invoices),
        },
        "breakdown": [
            {
                "period": period,
                "invoiced": str(data["invoiced"]),
                "invoiced_formatted": format_currency(data["invoiced"], "USD"),
                "paid": str(data["paid"]),
                "paid_formatted": format_currency(data["paid"], "USD"),
                "count": data["count"],
            }
            for period, data in sorted(by_period.items())
        ],
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
