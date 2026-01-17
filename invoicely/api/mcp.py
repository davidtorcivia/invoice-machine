"""MCP SSE endpoints for remote access via Claude Desktop."""

import secrets

from starlette.requests import Request
from starlette.responses import Response as StarletteResponse

from invoicely.database import async_session_maker, BusinessProfile


async def get_mcp_api_key() -> str | None:
    """Get the MCP API key from the database."""
    async with async_session_maker() as session:
        profile = await BusinessProfile.get(session)
        return profile.mcp_api_key if profile else None


async def verify_mcp_auth(request: Request) -> bool:
    """Verify MCP API key from request using constant-time comparison.

    Only accepts Bearer token authentication to avoid API key exposure in logs/URLs.
    """
    api_key = await get_mcp_api_key()

    # If no API key is configured, MCP is disabled for remote access
    if not api_key:
        return False

    # Check Authorization header (only Bearer token, no query params for security)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False

    provided_key = auth_header[7:]

    # Use constant-time comparison to prevent timing attacks
    return secrets.compare_digest(provided_key, api_key)


# Global SSE transport - initialized lazily
_sse_transport = None
_mcp_server = None


def get_sse_transport():
    """Get or create the SSE transport."""
    global _sse_transport, _mcp_server

    if _sse_transport is None:
        from mcp.server.sse import SseServerTransport
        from invoicely.mcp.server import mcp

        _sse_transport = SseServerTransport("/mcp/messages/")
        _mcp_server = mcp._mcp_server

    return _sse_transport, _mcp_server


async def mcp_sse_handler(scope, receive, send):
    """Raw ASGI handler for SSE endpoint - allows MCP transport to control response directly."""
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


async def mcp_messages_handler(scope, receive, send):
    """Raw ASGI handler for MCP messages - allows transport to control response directly."""
    request = Request(scope, receive, send)

    if not await verify_mcp_auth(request):
        response = StarletteResponse("MCP API key required", status_code=401)
        await response(scope, receive, send)
        return

    sse, _ = get_sse_transport()
    await sse.handle_post_message(scope, receive, send)


async def mcp_status_handler(scope, receive, send):
    """ASGI handler for MCP status endpoint."""
    import json

    api_key = await get_mcp_api_key()
    body = json.dumps({
        "enabled": bool(api_key),
        "endpoint": "/mcp/sse",
    })

    response = StarletteResponse(
        content=body,
        status_code=200,
        media_type="application/json"
    )
    await response(scope, receive, send)
