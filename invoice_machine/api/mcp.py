"""MCP SSE endpoints for remote access via Claude Desktop."""

from typing import Optional

from starlette.requests import Request
from starlette.responses import Response as StarletteResponse

from invoice_machine.database import async_session_maker, BusinessProfile
from invoice_machine.crypto import verify_api_key


async def get_mcp_api_key_hash() -> Optional[str]:
    """Get the MCP API key hash from the database."""
    async with async_session_maker() as session:
        profile = await BusinessProfile.get(session)
        return profile.mcp_api_key if profile else None


async def verify_mcp_auth(request: Request) -> bool:
    """Verify MCP API key from request using hash comparison.

    Only accepts Bearer token authentication to avoid API key exposure in logs/URLs.
    The stored key is hashed, so we verify by hashing the provided key.
    """
    stored_hash = await get_mcp_api_key_hash()

    # If no API key is configured, MCP is disabled for remote access
    if not stored_hash:
        return False

    # Check Authorization header (only Bearer token, no query params for security)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False

    provided_key = auth_header[7:]

    # Verify using hash comparison (supports both hashed and legacy unhashed keys)
    return verify_api_key(provided_key, stored_hash)


# Global SSE transport - initialized lazily
_sse_transport = None
_mcp_server = None


def get_sse_transport():
    """Get or create the SSE transport."""
    global _sse_transport, _mcp_server

    if _sse_transport is None:
        from mcp.server.sse import SseServerTransport
        from invoice_machine.mcp.server import mcp

        _sse_transport = SseServerTransport("/messages/")
        _mcp_server = mcp._mcp_server

    return _sse_transport, _mcp_server


class MCPSseHandler:
    """ASGI app for SSE endpoint - allows MCP transport to control response directly."""

    async def __call__(self, scope, receive, send):
        # SSE only supports GET - return 405 for other methods so client falls back to SSE transport
        if scope.get("method", "GET") != "GET":
            response = StarletteResponse("Method Not Allowed", status_code=405)
            await response(scope, receive, send)
            return

        request = Request(scope, receive, send)

        if not await verify_mcp_auth(request):
            response = StarletteResponse("MCP API key required", status_code=401)
            await response(scope, receive, send)
            return

        sse, mcp_server = get_sse_transport()

        async with sse.connect_sse(scope, receive, send) as streams:
            await mcp_server.run(
                streams[0], streams[1], mcp_server.create_initialization_options()
            )


class MCPMessagesHandler:
    """ASGI app for MCP messages - allows transport to control response directly."""

    async def __call__(self, scope, receive, send):
        request = Request(scope, receive, send)

        if not await verify_mcp_auth(request):
            response = StarletteResponse("MCP API key required", status_code=401)
            await response(scope, receive, send)
            return

        sse, _ = get_sse_transport()
        await sse.handle_post_message(scope, receive, send)


class MCPStatusHandler:
    """ASGI app for MCP status endpoint."""

    async def __call__(self, scope, receive, send):
        import json

        api_key_hash = await get_mcp_api_key_hash()
        body = json.dumps({
            "enabled": bool(api_key_hash),
            "endpoint": "/mcp/sse",
        })

        response = StarletteResponse(
            content=body,
            status_code=200,
            media_type="application/json"
        )
        await response(scope, receive, send)


# Instantiate the ASGI handlers
mcp_sse_handler = MCPSseHandler()
mcp_messages_handler = MCPMessagesHandler()
mcp_status_handler = MCPStatusHandler()
