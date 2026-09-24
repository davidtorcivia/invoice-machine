"""Document export and trash MCP tools."""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError

from invoice_machine.config import get_settings
from invoice_machine.service.common import list_trashed
from invoice_machine.service.invoices import InvoiceService

from .annotations import ADDITIVE_IDEMPOTENT, READ_ONLY
from .context import get_session, mcp

settings = get_settings()


@mcp.tool(annotations=ADDITIVE_IDEMPOTENT)
async def generate_pdf(invoice_id: int) -> dict:
    """Generate or regenerate the PDF for an invoice."""
    from invoice_machine.pdf.generator import store_invoice_pdf

    async with get_session() as session:
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            raise ToolError(f"Invoice {invoice_id} not found")

        # Explicit "regenerate" tool: always re-render.
        await store_invoice_pdf(session, invoice, force=True)
        generated_at = invoice.pdf_generated_at
        if generated_at is None:  # force=True always stamps it
            raise ToolError("PDF generation did not record a timestamp")

        return {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "pdf_url": f"{settings.app_base_url}/api/invoices/{invoice.id}/pdf",
            "generated_at": generated_at.isoformat(),
        }


@mcp.tool(annotations=READ_ONLY)
async def list_trash() -> list:
    """List trashed invoices and clients, with days until auto-purge."""
    async with get_session() as session:
        items = await list_trashed(session)
    return [{**item, "deleted_at": item["deleted_at"].isoformat()} for item in items]


# Note: empty_trash is intentionally not exposed via MCP for security reasons.
# Trash emptying is handled automatically by the scheduled cleanup task or via the web UI.
