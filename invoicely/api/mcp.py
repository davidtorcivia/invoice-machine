"""MCP SSE endpoints for remote access via Claude Desktop."""

import secrets

from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from starlette.responses import Response as StarletteResponse

from invoicely.database import async_session_maker, BusinessProfile

router = APIRouter(prefix="/mcp", tags=["mcp"])


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


@router.get("/sse")
async def mcp_sse(request: Request):
    """SSE endpoint for MCP connection."""
    if not await verify_mcp_auth(request):
        raise HTTPException(
            status_code=401,
            detail="MCP API key required. Configure it in Settings > MCP Integration."
        )

    sse, mcp_server = get_sse_transport()

    async def event_generator():
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(
                streams[0], streams[1], mcp_server.create_initialization_options()
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/messages/")
async def mcp_messages(request: Request):
    """Handle MCP messages."""
    if not await verify_mcp_auth(request):
        raise HTTPException(
            status_code=401,
            detail="MCP API key required. Configure it in Settings > MCP Integration."
        )

    sse, _ = get_sse_transport()
    await sse.handle_post_message(request.scope, request.receive, request._send)
    return Response(status_code=200)


@router.get("/status")
async def mcp_status():
    """Check MCP configuration status."""
    api_key = await get_mcp_api_key()
    return {
        "enabled": bool(api_key),
        "endpoint": "/mcp/sse",
    }
