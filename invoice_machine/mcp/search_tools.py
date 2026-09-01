"""Search MCP tools."""

from __future__ import annotations

from invoice_machine.services import SearchService

from .annotations import READ_ONLY
from .context import get_session, mcp


@mcp.tool(annotations=READ_ONLY)
async def search(
    query: str,
    search_invoices: bool = True,
    search_clients: bool = True,
    search_line_items: bool = True,
    limit: int = 20,
) -> dict:
    """
    Search across invoices, clients, and line items using full-text search.

    Supports partial matching and returns relevance-ranked results under
    'invoices', 'clients', and 'line_items', capped at `limit` per category.
    """
    async with get_session() as session:
        return await SearchService.search(
            session,
            query=query,
            search_invoices=search_invoices,
            search_clients=search_clients,
            search_line_items=search_line_items,
            limit=limit,
        )
