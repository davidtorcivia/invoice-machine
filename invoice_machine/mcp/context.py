"""Shared MCP server context."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession

import invoice_machine.database as db
from invoice_machine.runtime_schema import ensure_database_schema

mcp = FastMCP("invoice-machine")
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
