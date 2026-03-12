"""MCP server entry points and compatibility exports."""

from __future__ import annotations

# Import tool modules to register @mcp.tool() decorated functions.
# New tools added to any module are automatically registered.
from . import (  # noqa: F401
    analytics_tools,
    client_tools,
    document_tools,
    email_tools,
    invoice_tools,
    profile_tools,
    recurring_tools,
    search_tools,
)
from .context import mcp


def main():
    """Run the MCP server (stdio transport for local use)."""
    mcp.run()


def run_sse_server(host: str = "0.0.0.0", port: int = 8081):
    """
    Run the MCP server with SSE transport for remote access.

    This enables Claude Desktop to connect over HTTP from:
    - Another machine on your LAN
    - Remotely via Cloudflare Tunnel or similar

    Usage:
        python -m invoice_machine.mcp.server --sse --port 8081
    """
    import asyncio

    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.routing import Route

    from invoice_machine.api.mcp import get_mcp_api_key_hash, verify_mcp_auth

    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        if not await verify_mcp_auth(request):
            return Response("Unauthorized", status_code=401)

        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp._mcp_server.run(
                streams[0], streams[1], mcp._mcp_server.create_initialization_options()
            )
        return Response()

    async def handle_messages(request: Request):
        if not await verify_mcp_auth(request):
            return Response("Unauthorized", status_code=401)

        await sse.handle_post_message(request.scope, request.receive, request._send)
        return Response()

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages/", endpoint=handle_messages, methods=["POST"]),
        ]
    )

    print(f"Starting MCP SSE server on {host}:{port}")
    api_key_hash = asyncio.run(get_mcp_api_key_hash())
    if api_key_hash:
        print("API key authentication is ENABLED")
    else:
        print(
            "WARNING: No MCP API key configured - connections will be rejected until one is generated."
        )
    print(f"SSE endpoint: http://{host}:{port}/sse")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import sys

    if "--sse" in sys.argv:
        port = 8081
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
        run_sse_server(port=port)
    else:
        main()
