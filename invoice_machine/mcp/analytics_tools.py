"""Analytics MCP tools, delegating to service.analytics so MCP matches REST."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from mcp.server.mcpserver.exceptions import ToolError

from invoice_machine.service import analytics as analytics_service
from invoice_machine.service.clients import ClientService
from invoice_machine.service.common import format_currency, format_quantity, quantize_money
from invoice_machine.service.invoices import InvoiceService
from invoice_machine.utils import utc_now

from .annotations import READ_ONLY
from .context import get_session, mcp


@mcp.tool(annotations=READ_ONLY)
async def get_revenue_summary(
    from_date: str | None = None,
    to_date: str | None = None,
    group_by: str = "month",
) -> dict:
    """
    Get revenue summary for the specified period.

    Outstanding and overdue are point-in-time across all invoices; overdue
    counts "sent" invoices past their due date.

    Args:
        from_date: Start date (ISO format, defaults to start of current year)
        to_date: End date (ISO format, defaults to today)
        group_by: How to group breakdown - "month", "quarter", or "year"
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


@mcp.tool(annotations=READ_ONLY)
async def get_client_lifetime_value(
    client_id: int | None = None,
    limit: int = 20,
) -> list:
    """
    Get lifetime value for clients, in each client's dominant currency.

    Args:
        client_id: Specific client ID (returns single client if provided)
        limit: Maximum clients to return (default 20, sorted by total paid)
    """
    async with get_session() as session:
        return await analytics_service.client_lifetime_values(
            session, client_id=client_id, limit=limit
        )


@mcp.tool(annotations=READ_ONLY)
async def get_client_invoice_context(
    client_id: int,
    limit: int = 3,
) -> dict:
    """
    Get recent invoice history for a client, to draft new invoices matching
    their previous rates, descriptions, and payment terms.
    """
    async with get_session() as session:
        client = await ClientService.get_client(session, client_id)
        if not client:
            raise ToolError(f"Client {client_id} not found")

        invoices = await InvoiceService.list_invoices(
            session, client_id=client_id, document_type="invoice", limit=limit
        )
        # SQL aggregates in the client's dominant currency, the same figures REST reports.
        (stats,) = await ClientService.get_client_invoice_stats(session, client_id=client_id)
        currency = stats["currency"]
        scoped = stats["by_currency"].get(currency, {})
        total_billed = stats["total_invoiced"]
        total_paid = stats["total_paid"]
        billed_count = scoped.get("billed_invoice_count", 0)
        average_invoice = (
            quantize_money(total_billed / billed_count) if billed_count else Decimal("0.00")
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
                            "quantity": format_quantity(item.quantity),
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
                "currency": currency,
                "total_billed": str(total_billed),
                "total_billed_formatted": format_currency(total_billed, currency),
                "total_paid": str(total_paid),
                "total_paid_formatted": format_currency(total_paid, currency),
                "invoice_count": scoped.get("invoice_count", 0),
                "paid_count": scoped.get("paid_invoice_count", 0),
                "average_invoice": str(average_invoice),
                "average_invoice_formatted": format_currency(average_invoice, currency),
            },
        }


@mcp.tool(annotations=READ_ONLY)
async def get_consolidated_summary(
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """
    Single-currency roll-up of invoiced/paid/outstanding across all currencies.

    Every other money figure in this app is reported per-currency and never
    summed across currencies. This opt-in view converts each invoice using the
    exchange rate captured on it at issue time, and reports coverage: invoices
    with no recorded rate are EXCLUDED from the totals and counted separately,
    so a partial roll-up is never mistaken for a complete one. Check
    `coverage.complete` before quoting these numbers as a full picture.

    Args:
        from_date: Start date (ISO format, optional)
        to_date: End date (ISO format, optional)
    """
    async with get_session() as session:
        return await analytics_service.consolidated_summary(
            session,
            from_date_parsed=date.fromisoformat(from_date) if from_date else None,
            to_date_parsed=date.fromisoformat(to_date) if to_date else None,
        )
