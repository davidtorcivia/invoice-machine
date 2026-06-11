"""FastAPI application entry point."""

import asyncio
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.applications import Starlette
from starlette.routing import Route

from invoice_machine.api import (
    analytics,
    auth,
    backup,
    clients,
    email,
    email_templates,
    invoices,
    mcp,
    profile,
    recurring,
    search,
    trash,
)
from invoice_machine.app_middleware import configure_http_middleware
from invoice_machine.app_runtime import lifespan
from invoice_machine.config import get_settings
from invoice_machine.skill_manifest import render_skill_manifest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

settings = get_settings()
STATIC_DIR = Path("invoice_machine/static")
STATIC_DIR_RESOLVED = STATIC_DIR.resolve()

app = FastAPI(
    title="Invoice Machine",
    description="AI-first invoicing application",
    version="0.1.0",
    lifespan=lifespan,
)
app.state.restore_lock = asyncio.Lock()
app.state.restore_in_progress = False
app.state.active_requests = 0

configure_http_middleware(app)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(clients.router)
app.include_router(invoices.router)
app.include_router(trash.router)
app.include_router(backup.router)
app.include_router(recurring.router)
app.include_router(email.router)
app.include_router(email_templates.router)
app.include_router(search.router)
app.include_router(analytics.router)

# Streamable HTTP is the primary MCP transport. It must be an exact "/mcp"
# route on the main app (not a route inside the mount below) because hitting a
# mount root triggers a 307 redirect that not all MCP clients follow.
app.add_route("/mcp", mcp.mcp_streamable_http_handler, methods=["POST", "GET", "DELETE"])

mcp_asgi_app = Starlette(
    routes=[
        # Legacy SSE transport, kept for existing client configs.
        Route("/sse", endpoint=mcp.mcp_sse_handler),
        Route("/messages/", endpoint=mcp.mcp_messages_handler, methods=["POST"]),
        Route("/status", endpoint=mcp.mcp_status_handler),
    ]
)
app.mount("/mcp", mcp_asgi_app)


@app.get("/health")
async def health_check(request: Request):
    """Health check: verifies the app can reach the database.

    Skips the DB check while a backup restore is swapping the database file so
    the container isn't marked unhealthy (and restarted) mid-restore.
    """
    if getattr(request.app.state, "restore_in_progress", False):
        return {"status": "healthy"}

    from sqlalchemy import text

    from invoice_machine.database import async_session_maker

    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "unhealthy"}, status_code=503)
    return {"status": "healthy"}


@app.get("/SKILL.md", include_in_schema=False)
async def skill_manifest(request: Request):
    """Serve a comprehensive skill manifest for bot integrations."""
    base_url = str(request.base_url).rstrip("/")
    content = render_skill_manifest(base_url)
    return Response(content, media_type="text/markdown")


@app.get("/{path:path}")
async def serve_spa(path: str):
    """Serve static files or fall back to index.html for SPA routing."""
    # Try to serve the exact file
    if path:
        file_path = (STATIC_DIR / path).resolve()
        try:
            file_path.relative_to(STATIC_DIR_RESOLVED)
        except ValueError:
            return JSONResponse({"detail": "Not found"}, status_code=404)

        if file_path.is_file():
            return FileResponse(file_path)

    # Fall back to index.html for SPA routes
    index_path = STATIC_DIR / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)

    return JSONResponse({"detail": "Not found"}, status_code=404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("invoice_machine.main:app", host="0.0.0.0", port=8080, reload=True)

