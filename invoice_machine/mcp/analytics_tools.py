"""Analytics MCP tools."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional, Union

from invoice_machine.database import Client
from invoice_machine.services import ClientService, InvoiceService, format_currency, is_invoice_document

from .context import get_session, mcp

@mcp.tool()
async def get_revenue_summary(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    group_by: str = "month",
) -> dict:
    """
    Get revenue summary for the specified period.

    Args:
        from_date: Start date (ISO format, defaults to start of current year)
        to_date: End date (ISO format, defaults to today)
        group_by: How to group breakdown - "month", "quarter", or "year"

    Returns:
        Total invoiced, paid, outstanding, and breakdown by period
    """
    from collections import defaultdict

    async with get_session() as session:
        # Parse dates
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

        invoices = [inv for inv in invoices if is_invoice_document(inv)]

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
                "overdue": str(total_overdue),
                "invoice_count": len(invoices),
            },
            "by_period": {
                k: {
                    "invoiced": str(v["invoiced"]),
                    "paid": str(v["paid"]),
                    "count": v["count"],
                }
                for k, v in sorted(by_period.items())
            },
        }


@mcp.tool()
async def get_client_lifetime_value(
    client_id: Optional[int] = None,
    limit: int = 20,
) -> list:
    """
    Get lifetime value for clients.

    Args:
        client_id: Specific client ID (returns single client if provided)
        limit: Maximum clients to return (default 20, sorted by total paid)

    Returns:
        List of clients with their total invoiced, paid, and invoice counts
    """
    async with get_session() as session:
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

            invoices = [inv for inv in invoices if is_invoice_document(inv)]

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


@mcp.tool()
async def get_client_invoice_context(
    client_id: int,
    limit: int = 3,
) -> dict:
    """
    Get context for drafting a new invoice for a client.

    This provides recent invoice history to help draft invoices that match
    previous patterns (rates, descriptions, payment terms).

    Args:
        client_id: The client ID
        limit: Number of recent invoices to include (default 3)

    Returns:
        Client details, recent invoices with line items, and statistics
    """
    async with get_session() as session:
        client = await ClientService.get_client(session, client_id)
        if not client:
            return {"error": "Client not found"}

        # Get recent invoices
        invoices = await InvoiceService.list_invoices(
            session,
            client_id=client_id,
            limit=limit,
        )
        invoices = [inv for inv in invoices if is_invoice_document(inv)]

        # Get all invoices for stats
        all_invoices = await InvoiceService.list_invoices(
            session,
            client_id=client_id,
            limit=10000,
        )

        all_invoices = [inv for inv in all_invoices if is_invoice_document(inv)]

        total_billed = sum(inv.total for inv in all_invoices if inv.status in ("sent", "paid", "overdue"))
        paid_invoices = [inv for inv in all_invoices if inv.status == "paid"]
        total_paid = sum(inv.total for inv in paid_invoices)

        return {
            "client": {
                "id": client.id,
                "name": client.name,
                "business_name": client.business_name,
                "display_name": client.display_name,
                "email": client.email,
                "payment_terms_days": client.payment_terms_days,
            },
            "recent_invoices": [
                {
                    "invoice_number": inv.invoice_number,
                    "issue_date": inv.issue_date.isoformat(),
                    "total": str(inv.total),
                    "total_formatted": format_currency(inv.total, inv.currency_code),
                    "status": inv.status,
                    "currency_code": inv.currency_code,
                    "items": [
                        {
                            "description": item.description,
                            "quantity": item.quantity,
                            "unit_type": getattr(item, "unit_type", "qty"),
                            "unit_price": str(item.unit_price),
                            "total": str(item.total),
                        }
                        for item in inv.items
                    ],
                }
                for inv in invoices
            ],
            "statistics": {
                "total_billed": str(total_billed),
                "total_billed_formatted": format_currency(total_billed, "USD"),
                "total_paid": str(total_paid),
                "total_paid_formatted": format_currency(total_paid, "USD"),
                "invoice_count": len(all_invoices),
                "paid_count": len(paid_invoices),
                "average_invoice": str(total_billed / len(all_invoices)) if all_invoices else "0",
            },
        }



