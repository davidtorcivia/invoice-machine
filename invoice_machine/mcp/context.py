"""Shared MCP server context."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server import MCPServer
from mcp.server.caching import CacheHint
from sqlalchemy.ext.asyncio import AsyncSession

import invoice_machine.database as db
from invoice_machine import __version__
from invoice_machine.runtime_schema import ensure_database_schema

# Transport options belong on run()/streamable_http_app(), not the constructor.
mcp = MCPServer(
    "invoice-machine",
    version=__version__,
    # Spec 2026-07-28 requires ttlMs/cacheScope on list results (SEP-2549); the
    # SDK otherwise stamps ttl_ms=0, telling clients never to cache. "private"
    # keeps shared proxies from caching a self-hosted instance's inventory.
    cache_hints={
        "tools/list": CacheHint(ttl_ms=300_000, scope="private"),
        "server/discover": CacheHint(ttl_ms=300_000, scope="private"),
        # Lists only - resources/read stays uncached, because an invoice's
        # contents change whenever someone records a payment against it.
        "prompts/list": CacheHint(ttl_ms=300_000, scope="private"),
        "resources/list": CacheHint(ttl_ms=300_000, scope="private"),
        "resources/templates/list": CacheHint(ttl_ms=300_000, scope="private"),
    },
)
_schema_initialized = False


async def ensure_mcp_schema_initialized() -> None:
    """Initialize the database once for standalone MCP usage."""
    global _schema_initialized
    if _schema_initialized:
        return
    await ensure_database_schema(apply_migrations=True)
    _schema_initialized = True


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an initialized async database session."""
    await ensure_mcp_schema_initialized()
    async with db.async_session_maker() as session:
        yield session
