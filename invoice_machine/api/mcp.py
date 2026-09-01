"""MCP remote-access endpoints (Streamable HTTP + legacy SSE)."""

from contextlib import asynccontextmanager

from starlette.requests import Request
from starlette.responses import Response as StarletteResponse

from invoice_machine.api_keys import authenticate_api_key, count_api_keys
from invoice_machine.rate_limit import bearer_auth_throttle, get_client_ip


async def verify_mcp_auth(request: Request) -> bool:
    """Verify an MCP API key from the request against the stored key hashes.

    Only accepts Bearer token authentication to avoid API key exposure in logs/URLs.
    """
    # Brute-force/DoS protection per client IP (process-local; single-worker).
    client_ip = get_client_ip(request)
    if bearer_auth_throttle.is_blocked(client_ip):
        return False

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False

    result = await authenticate_api_key("mcp", auth_header[7:])
    if not result:
        bearer_auth_throttle.record_failure(client_ip)
    return result


# Streamable HTTP session manager - created by streamable_http_lifespan().
# None whenever the lifespan isn't running (startup/shutdown), so the handler
# can answer 503 instead of crashing.
_http_session_manager = None


@asynccontextmanager
async def streamable_http_lifespan():
    """Run the Streamable HTTP session manager for the app's lifetime.

    A StreamableHTTPSessionManager cannot be reused after its run() context
    exits, so a fresh instance is created on every entry (the app lifespan runs
    once per process in production, but repeatedly across tests).
    """
    global _http_session_manager

    from mcp.server.transport_security import TransportSecuritySettings

    from invoice_machine.mcp.server import mcp

    # Called for its side effect of building a fresh session manager on
    # mcp.session_manager; the Starlette app it returns is unused, because the
    # endpoint is served through MCPStreamableHTTPHandler so Bearer auth runs first.
    mcp.streamable_http_app(
        # Stateless: every MCP call is an independent POST with no server-side
        # session, so proxies dropping idle connections cannot strand a client.
        json_response=True,
        stateless_http=True,
        # Host is validated at the reverse proxy and the public hostname is
        # deployment-specific, so the SDK's DNS-rebinding check stays off.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    manager = mcp.session_manager
    _http_session_manager = manager
    try:
        async with manager.run():
            yield
    finally:
        _http_session_manager = None


class MCPStreamableHTTPHandler:
    """ASGI app for the Streamable HTTP endpoint (modern MCP transport)."""

    async def __call__(self, scope, receive, send):
        request = Request(scope, receive, send)

        if not await verify_mcp_auth(request):
            response = StarletteResponse("MCP API key required", status_code=401)
            await response(scope, receive, send)
            return

        if _http_session_manager is None:
            response = StarletteResponse("MCP server not ready", status_code=503)
            await response(scope, receive, send)
            return

        await _http_session_manager.handle_request(scope, receive, send)


_sse_transport = None
_mcp_server = None


def get_sse_transport():
    """Get or create the SSE transport."""
    global _sse_transport, _mcp_server

    if _sse_transport is None:
        from mcp.server.sse import SseServerTransport

        from invoice_machine.mcp.server import mcp

        # security_settings=None leaves DNS-rebinding checks off, matching the
        # Streamable HTTP endpoint above (Host is validated at the proxy).
        _sse_transport = SseServerTransport("/messages/")
        _mcp_server = mcp._lowlevel_server

    return _sse_transport, _mcp_server


class MCPSseHandler:
    """ASGI app for SSE endpoint - allows MCP transport to control response directly."""

    async def __call__(self, scope, receive, send):
        # SSE is GET-only; a 405 makes the client fall back to the SSE transport.
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
            await mcp_server.run(streams[0], streams[1], mcp_server.create_initialization_options())


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

        from mcp_types import DEFAULT_NEGOTIATED_VERSION, LATEST_PROTOCOL_VERSION

        body = json.dumps(
            {
                "enabled": await count_api_keys("mcp") > 0,
                "endpoint": "/mcp",
                "transport": "streamable-http",
                "legacy_sse_endpoint": "/mcp/sse",
                # One endpoint serves both protocol eras: modern clients send a
                # self-describing request, older ones still get the handshake.
                "protocol_version": LATEST_PROTOCOL_VERSION,
                "supported_protocol_versions": [
                    DEFAULT_NEGOTIATED_VERSION,
                    LATEST_PROTOCOL_VERSION,
                ],
            }
        )

        response = StarletteResponse(content=body, status_code=200, media_type="application/json")
        await response(scope, receive, send)


mcp_streamable_http_handler = MCPStreamableHTTPHandler()
mcp_sse_handler = MCPSseHandler()
mcp_messages_handler = MCPMessagesHandler()
mcp_status_handler = MCPStatusHandler()
