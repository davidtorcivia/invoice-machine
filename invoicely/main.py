"""FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from invoicely.config import get_settings
from invoicely.database import init_db, close_db
from invoicely.api import profile, clients, invoices, trash, auth, mcp, backup
from invoicely.api.auth import get_session_user_id, SESSION_COOKIE_NAME, cleanup_expired_sessions

settings = get_settings()
STATIC_DIR = Path("invoicely/static")

# Paths that don't require authentication
PUBLIC_PATHS = {"/health", "/api/auth/status", "/api/auth/setup", "/api/auth/login", "/api/auth/logout"}

# Paths that use MCP API key authentication instead of session
MCP_PATHS_PREFIX = "/mcp/"


async def session_cleanup_task():
    """Background task to cleanup expired sessions every hour."""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        cleanup_expired_sessions()


async def scheduled_backup_task():
    """Background task to run daily backups at midnight UTC."""
    from datetime import datetime, timedelta
    from invoicely.database import async_session_maker, BusinessProfile
    from invoicely.services.backup import BackupService
    import json

    while True:
        # Calculate seconds until next midnight UTC
        now = datetime.utcnow()
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_until_midnight = (next_midnight - now).total_seconds()

        await asyncio.sleep(seconds_until_midnight)

        # Check if backups are enabled and run backup
        try:
            async with async_session_maker() as session:
                profile = await BusinessProfile.get(session)
                if profile and profile.backup_enabled:
                    # Get S3 config if enabled
                    s3_config = None
                    if profile.backup_s3_enabled and profile.backup_s3_config:
                        try:
                            s3_config = json.loads(profile.backup_s3_config)
                            s3_config["enabled"] = True
                        except json.JSONDecodeError:
                            pass

                    backup_service = BackupService(
                        retention_days=profile.backup_retention_days or 30,
                        s3_config=s3_config,
                    )

                    # Create backup
                    backup_service.create_backup(compress=True)

                    # Cleanup old backups
                    backup_service.cleanup_old_backups()
        except Exception:
            pass  # Don't crash on backup failures


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager."""
    # Startup - run migrations first
    from invoicely.migrations.add_new_fields import migrate
    migrate(settings.data_dir / "invoicely.db")

    await init_db()

    # Start background tasks
    cleanup_task = asyncio.create_task(session_cleanup_task())
    backup_task = asyncio.create_task(scheduled_backup_task())

    yield

    # Shutdown
    cleanup_task.cancel()
    backup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    try:
        await backup_task
    except asyncio.CancelledError:
        pass
    await close_db()


app = FastAPI(
    title="Invoice Machine",
    description="AI-first invoicing application",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware - configured from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Protect API routes with authentication."""
    path = request.url.path

    # Allow public paths and non-API routes
    if path in PUBLIC_PATHS or not path.startswith("/api/"):
        return await call_next(request)

    # MCP endpoints use their own API key authentication
    if path.startswith(MCP_PATHS_PREFIX):
        return await call_next(request)

    # Check session cookie
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        return JSONResponse(
            {"detail": "Authentication required"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    user_id = get_session_user_id(session_token)
    if not user_id:
        return JSONResponse(
            {"detail": "Session expired"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    return await call_next(request)


# Include routers
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(clients.router)
app.include_router(invoices.router)
app.include_router(trash.router)
app.include_router(backup.router)
app.include_router(mcp.router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/{path:path}")
async def serve_spa(path: str):
    """Serve static files or fall back to index.html for SPA routing."""
    # Try to serve the exact file
    file_path = STATIC_DIR / path
    if file_path.is_file():
        return FileResponse(file_path)

    # Fall back to index.html for SPA routes
    index_path = STATIC_DIR / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)

    return JSONResponse({"detail": "Not found"}, status_code=404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("invoicely.main:app", host="0.0.0.0", port=8080, reload=True)
