"""Analytics MCP tools.

These delegate to invoice_machine.service.analytics so MCP results match the
REST analytics endpoints exactly (currency-aware, consistent overdue logic).
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal

from invoice_machine.service import analytics as analytics_service
from invoice_machine.services import (
    ClientService,
    InvoiceService,
    format_currency,
    is_invoice_document,
    quantize_money,
)
from invoice_machine.utils import utc_now

from .context import get_session, mcp


@mcp.tool()
async def get_revenue_summary(
    from_date: str | None = None,
    to_date: str | None = None,
    group_by: str = "month",
) -> dict:
    """
    Get revenue summary for the specified period.

    Args:
        from_date: Start date (ISO format, defaults to start of current year)
        to_date: End date (ISO format, defaults to today)
        group_by: How to group breakdown - "month", "quarter", or "year"

    Returns:
        Total invoiced, paid, outstanding, overdue (per currency), and a period
        breakdown. Outstanding/overdue are point-in-time across all invoices;
        overdue counts "sent" invoices past their due date.
    """
    if group_by not in ("month", "quarter", "year"):
        raise ValueError('group_by must be "month", "quarter", or "year"')
    async with get_session() as session:
        today = utc_now().date()
        from_date_parsed = date.fromisoformat(from_date) if from_date else date(today.year, 1, 1)
        to_date_parsed = date.fromisoformat(to_date) if to_date else today
        return await analytics_service.revenue_summary(
            session, from_date_parsed, to_date_parsed, group_by
        )


@mcp.tool()
async def get_client_lifetime_value(
    client_id: int | None = None,
    limit: int = 20,
) -> list:
    """
    Get lifetime value for clients.

    Args:
        client_id: Specific client ID (returns single client if provided)
        limit: Maximum clients to return (default 20, sorted by total paid)

    Returns:
        List of clients with total invoiced/paid in their dominant currency,
        a per-currency breakdown, and invoice counts.
    """
    async with get_session() as session:
        return await analytics_service.client_lifetime_values(
            session, client_id=client_id, limit=limit
        )


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

        # Scope statistics to the client's dominant currency so totals/averages
        # are never a mix of currencies.
        cur_counts = Counter(inv.currency_code for inv in all_invoices)
        dominant_currency = (
            cur_counts.most_common(1)[0][0]
            if cur_counts
            else (client.preferred_currency or "USD")
        )
        scoped = [inv for inv in all_invoices if inv.currency_code == dominant_currency]
        billable = [inv for inv in scoped if inv.status in ("sent", "paid", "overdue")]
        total_billed = sum((inv.total for inv in billable), Decimal("0"))
        paid_invoices = [inv for inv in scoped if inv.status == "paid"]
        total_paid = sum((inv.total for inv in paid_invoices), Decimal("0"))
        # Average over BILLABLE invoices (not drafts/cancelled, not all docs).
        average_invoice = (
            quantize_money(total_billed / len(billable)) if billable else Decimal("0.00")
        )

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
                "currency": dominant_currency,
                "total_billed": str(quantize_money(total_billed)),
                "total_billed_formatted": format_currency(total_billed, dominant_currency),
                "total_paid": str(quantize_money(total_paid)),
                "total_paid_formatted": format_currency(total_paid, dominant_currency),
                "invoice_count": len(scoped),
                "paid_count": len(paid_invoices),
                "average_invoice": str(average_invoice),
                "average_invoice_formatted": format_currency(average_invoice, dominant_currency),
            },
        }



