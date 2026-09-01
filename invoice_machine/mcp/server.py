"""MCP server entry points and compatibility exports."""

from __future__ import annotations

import logging

# Import tool modules to register @mcp.tool() decorated functions, plus the
# resource and prompt modules. New tools added to any module are automatically
# registered.
from . import (  # noqa: F401
    analytics_tools,
    client_tools,
    document_tools,
    email_tools,
    export_tools,
    invoice_tools,
    payment_tools,
    profile_tools,
    prompts,
    recurring_tools,
    resources,
    search_tools,
)
from .context import mcp

logger = logging.getLogger(__name__)


def main():
    """Run the MCP server (stdio transport for local use)."""
    mcp.run()


def run_http_server(host: str = "0.0.0.0", port: int = 8081):
    """
    Run a standalone MCP server over Streamable HTTP for remote access.

    This enables Claude Desktop and other MCP clients to connect over HTTP from:
    - Another machine on your LAN
    - Remotely via Cloudflare Tunnel or similar

    Prefer running the main web app, which already serves /mcp on the same port.
    This entry point exists for deployments that want MCP on its own port.

    Usage:
        python -m invoice_machine.mcp.server --http --port 8081
    """
    import asyncio

    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.requests import Request
    from starlette.responses import Response as StarletteResponse

    from invoice_machine.api.mcp import verify_mcp_auth
    from invoice_machine.api_keys import count_api_keys

    # Same configuration as the endpoint mounted in the main app: stateless
    # JSON-over-POST, with Host validation left to the reverse proxy.
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    class BearerAuth:
        """Reject unauthenticated requests before they reach the MCP app.

        Wraps the app rather than mounting it, so /mcp stays the exact path a
        client posts to - a Mount would answer POST /mcp with a 307 to /mcp/.
        Non-HTTP scopes (notably lifespan, which starts the session manager)
        pass straight through.
        """

        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            if not await verify_mcp_auth(Request(scope, receive, send)):
                response = StarletteResponse("Unauthorized", status_code=401)
                await response(scope, receive, send)
                return
            await self.app(scope, receive, send)

    app = BearerAuth(mcp_app)

    logger.info("Starting MCP Streamable HTTP server on %s:%s", host, port)

    async def read_key_count():
        # Create the schema first: on a fresh database the api_keys table does
        # not exist yet, and querying it here would kill the process before
        # uvicorn ever binds.
        from .context import ensure_mcp_schema_initialized

        await ensure_mcp_schema_initialized()
        return await count_api_keys("mcp")

    if asyncio.run(read_key_count()):
        logger.info("MCP API key authentication is ENABLED")
    else:
        logger.warning(
            "No MCP API key configured - connections will be rejected until one is generated."
        )
    logger.info("MCP endpoint: http://%s:%s/mcp", host, port)

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import sys

    # --sse is the pre-2026 spelling; the SSE transport is deprecated, so it
    # now starts the Streamable HTTP server that superseded it.
    if "--http" in sys.argv or "--sse" in sys.argv:
        port = 8081
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
        run_http_server(port=port)
    else:
        main()
