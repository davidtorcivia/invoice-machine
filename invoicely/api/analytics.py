"""Analytics API endpoints."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from invoicely.database import get_session
from invoicely.services import InvoiceService, ClientService, format_currency

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/revenue")
async def get_revenue_summary(
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
        limit=10000,
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
async def get_client_lifetime_values(
    client_id: Optional[int] = Query(None, description="Specific client ID"),
    limit: int = Query(20, ge=1, le=100, description="Max clients to return"),
    session: AsyncSession = Depends(get_session),
) -> list:
    """
    Get lifetime value for clients.

    Returns list of clients with total invoiced, paid, and invoice counts.
    Sorted by total paid descending.
    """
    if client_id:
        client = await ClientService.get_client(session, client_id)
        clients = [client] if client else []
    else:
        clients = await ClientService.list_clients(session)

    results = []
    for client in clients:
        if not client:
            continue

        invoices = await InvoiceService.list_invoices(
            session, client_id=client.id, limit=10000
        )

        total_invoiced = sum(inv.total for inv in invoices)
        total_paid = sum(inv.total for inv in invoices if inv.status == "paid")
        paid_invoices = [inv for inv in invoices if inv.status == "paid"]

        results.append({
            "client_id": client.id,
            "name": client.display_name,
            "email": client.email,
            "total_invoiced": str(total_invoiced),
            "total_invoiced_formatted": format_currency(total_invoiced, "USD"),
            "total_paid": str(total_paid),
            "total_paid_formatted": format_currency(total_paid, "USD"),
            "invoice_count": len(invoices),
            "paid_invoice_count": len(paid_invoices),
            "first_invoice": min(inv.issue_date for inv in invoices).isoformat() if invoices else None,
            "last_invoice": max(inv.issue_date for inv in invoices).isoformat() if invoices else None,
        })

    # Sort by total paid (descending) and limit
    results.sort(key=lambda x: Decimal(x["total_paid"]), reverse=True)
    return results[:limit]
