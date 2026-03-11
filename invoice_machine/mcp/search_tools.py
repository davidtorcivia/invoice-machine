"""Search MCP tools."""

from __future__ import annotations

from invoice_machine.services import SearchService

from .context import get_session, mcp


@mcp.tool()
async def search(
    query: str,
    search_invoices: bool = True,
    search_clients: bool = True,
    search_line_items: bool = True,
    limit: int = 20,
) -> dict:
    """
    Search across invoices, clients, and line items using full-text search.

    Supports partial matching and returns relevance-ranked results.

    Args:
        query: Search query (e.g., "acme", "consulting", "INV-2025")
        search_invoices: Include invoices in search (default: True)
        search_clients: Include clients in search (default: True)
        search_line_items: Include invoice line items in search (default: True)
        limit: Maximum results per category (default: 20)

    Returns:
        Dict with 'invoices', 'clients', and 'line_items' lists containing matching results
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



