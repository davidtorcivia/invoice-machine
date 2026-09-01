"""CSV export MCP tools."""

from __future__ import annotations

from datetime import date

from mcp.server.mcpserver.exceptions import ToolError

from invoice_machine.service.export import EXPORT_KINDS, export_csv_text

from .annotations import READ_ONLY
from .context import get_session, mcp

# Cap MCP exports so a large ledger can't be pulled wholesale into a model
# context. The REST endpoint streams the full export with no cap.
_MCP_MAX_ROWS = 500


@mcp.tool(annotations=READ_ONLY)
async def export_csv(
    kind: str = "invoices",
    from_date: str | None = None,
    to_date: str | None = None,
    include_deleted: bool = False,
    document_type: str | None = None,
    max_rows: int = 500,
) -> dict:
    """
    Export records as CSV text for accounting or spreadsheet use.

    Money is emitted as plain decimal strings with an explicit currency column;
    amounts in different currencies are never combined.

    Args:
        kind: One of "invoices", "line_items", "payments", "clients"
        from_date: Filter from this date, inclusive (ISO format)
        to_date: Filter to this date, inclusive (ISO format)
        include_deleted: Include trashed records
        document_type: Restrict to "invoice" or "quote" (invoices/line_items only)
        max_rows: Maximum data rows to return (capped at 500)
    """
    if kind not in EXPORT_KINDS:
        raise ToolError(f"Unknown export kind '{kind}'. Available: {list(EXPORT_KINDS)}")

    limit = max(1, min(int(max_rows), _MCP_MAX_ROWS))

    async with get_session() as session:
        csv_text = await export_csv_text(
            session,
            kind,
            from_date=date.fromisoformat(from_date) if from_date else None,
            to_date=date.fromisoformat(to_date) if to_date else None,
            include_deleted=include_deleted,
            document_type=document_type,
            max_rows=limit,
        )

    return {
        "kind": kind,
        "csv": csv_text,
        "truncated": "# truncated at" in csv_text,
        "note": ("Use the REST endpoint /api/export/{kind}.csv for a full, unbounded export."),
    }
