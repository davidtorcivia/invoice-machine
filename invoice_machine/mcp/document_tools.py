"""Document export and trash MCP tools."""

from __future__ import annotations

from invoice_machine.config import get_settings
from invoice_machine.database import Client, Invoice
from invoice_machine.services import InvoiceService
from invoice_machine.utils import ensure_utc, utc_now

from .context import get_session, mcp

settings = get_settings()

@mcp.tool()
async def generate_pdf(invoice_id: int) -> dict:
    """
    Generate or regenerate PDF for an invoice.

    Args:
        invoice_id: The invoice's ID

    Returns:
        {
            "invoice_id": 123,
            "invoice_number": "20250115-1",
            "pdf_url": "http://localhost:8080/api/invoices/123/pdf",
            "generated_at": "2025-01-15T10:30:00Z"
        }
    """
    from invoice_machine.pdf.generator import generate_pdf as do_generate_pdf

    async with get_session() as session:
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            return {"error": "Invoice not found"}

        pdf_path = await do_generate_pdf(session, invoice)

        invoice.pdf_path = pdf_path
        invoice.pdf_generated_at = utc_now()
        await session.commit()

        return {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "pdf_url": f"{settings.app_base_url}/api/invoices/{invoice.id}/pdf",
            "generated_at": invoice.pdf_generated_at.isoformat(),
        }


# ============================================================================
# Trash Management
# ============================================================================


@mcp.tool()
async def list_trash() -> list:
    """
    List all trashed invoices and clients.

    Returns:
        List of trashed items with days until auto-purge
    """
    async with get_session() as session:
        from sqlalchemy import select

        now = utc_now()
        items = []

        # Trashed clients
        client_result = await session.execute(
            select(Client).where(
                Client.deleted_at.is_not(None)
            )
        )
        for client in client_result.scalars():
            deleted_at = ensure_utc(client.deleted_at)
            if not deleted_at:
                continue
            days_left = settings.trash_retention_days - int(
                (now - deleted_at).total_seconds() / 86400
            )
            items.append({
                "type": "client",
                "id": client.id,
                "name": client.display_name,
                "deleted_at": deleted_at.isoformat(),
                "days_until_purge": days_left,
            })

        # Trashed invoices
        invoice_result = await session.execute(
            select(Invoice).where(
                Invoice.deleted_at.is_not(None)
            )
        )
        for invoice in invoice_result.scalars():
            deleted_at = ensure_utc(invoice.deleted_at)
            if not deleted_at:
                continue
            days_left = settings.trash_retention_days - int(
                (now - deleted_at).total_seconds() / 86400
            )
            items.append({
                "type": "invoice",
                "id": invoice.id,
                "name": invoice.invoice_number,
                "deleted_at": deleted_at.isoformat(),
                "days_until_purge": days_left,
            })

        items.sort(key=lambda x: x["deleted_at"], reverse=True)
        return items


# Note: empty_trash is intentionally not exposed via MCP for security reasons.
# Trash emptying is handled automatically by the scheduled cleanup task or via the web UI.


