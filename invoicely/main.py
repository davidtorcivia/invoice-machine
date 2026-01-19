"""FastAPI application entry point."""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status

# Configure logging with proper handlers
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from invoicely.config import get_settings
from invoicely.rate_limit import limiter
from invoicely.database import init_db, close_db
from starlette.routing import Route
from invoicely.api import profile, clients, invoices, trash, auth, mcp, backup, recurring, email, search, analytics
from invoicely.api.auth import get_session_user_id, SESSION_COOKIE_NAME, cleanup_expired_sessions

settings = get_settings()
STATIC_DIR = Path("invoicely/static")

# Paths that don't require authentication
PUBLIC_PATHS = {"/health", "/api/auth/status", "/api/auth/setup", "/api/auth/login", "/api/auth/logout"}


async def session_cleanup_task():
    """Background task to cleanup expired sessions every hour."""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        cleanup_expired_sessions()


async def scheduled_backup_task():
    """Background task to run daily backups at midnight UTC."""
    from datetime import datetime, timedelta
    from invoicely.database import async_session_maker, BusinessProfile
    from invoicely.services import BackupService
    import json

    while True:
        # Calculate seconds until next midnight UTC
        now = datetime.utcnow()
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_until_midnight = (next_midnight - now).total_seconds()

        await asyncio.sleep(seconds_until_midnight)


async def trash_cleanup_task():
    """Background task to auto-purge expired trash items daily at 3 AM UTC."""
    from datetime import datetime, timedelta
    from invoicely.tasks.cleanup_trash import cleanup_trash

    while True:
        # Calculate seconds until next 3 AM UTC
        now = datetime.utcnow()
        next_3am = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if now.hour >= 3:
            next_3am = next_3am + timedelta(days=1)
        seconds_until_3am = (next_3am - now).total_seconds()

        await asyncio.sleep(seconds_until_3am)

        try:
            await cleanup_trash()
        except Exception as e:
            logger.error(f"Trash cleanup task failed: {e}", exc_info=True)


async def overdue_check_task():
    """Background task to mark overdue invoices daily at 1 AM UTC."""
    from datetime import datetime, timedelta
    from invoicely.database import async_session_maker
    from invoicely.services import InvoiceService

    while True:
        # Calculate seconds until next 1 AM UTC
        now = datetime.utcnow()
        next_1am = now.replace(hour=1, minute=0, second=0, microsecond=0)
        if now.hour >= 1:
            next_1am = next_1am + timedelta(days=1)
        seconds_until_1am = (next_1am - now).total_seconds()

        await asyncio.sleep(seconds_until_1am)

        try:
            async with async_session_maker() as session:
                count = await InvoiceService.update_overdue_invoices(session)
                if count > 0:
                    logger.info(f"Marked {count} invoices as overdue")
        except Exception as e:
            logger.error(f"Overdue check task failed: {e}", exc_info=True)


async def recurring_invoice_task():
    """Background task to process recurring invoices daily at 2 AM UTC."""
    from datetime import datetime, timedelta
    from invoicely.database import async_session_maker
    from invoicely.services import RecurringService

    while True:
        # Calculate seconds until next 2 AM UTC
        now = datetime.utcnow()
        next_2am = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if now.hour >= 2:
            next_2am = next_2am + timedelta(days=1)
        seconds_until_2am = (next_2am - now).total_seconds()

        await asyncio.sleep(seconds_until_2am)

        try:
            async with async_session_maker() as session:
                results = await RecurringService.process_due_schedules(session)
                if results:
                    success_count = sum(1 for r in results if r.get("success"))
                    logger.info(f"Processed {len(results)} recurring schedules, {success_count} invoices created")
        except Exception as e:
            logger.error(f"Recurring invoice task failed: {e}", exc_info=True)

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
                    logger.info("Scheduled backup completed successfully")
        except Exception as e:
            logger.error(f"Scheduled backup task failed: {e}", exc_info=True)


def run_alembic_migrations():
    """Run Alembic migrations to upgrade database schema."""
    from alembic.config import Config
    from alembic import command
    from pathlib import Path
    import sqlite3

    # Get the alembic.ini path relative to project root
    project_root = Path(__file__).parent.parent
    alembic_cfg = Config(str(project_root / "alembic.ini"))

    # Check if database exists and has tables but no valid alembic version
    db_path = settings.data_dir / "invoicely.db"
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Check if alembic_version table exists AND has a version row
            # (A failed migration can leave an empty alembic_version table)
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            )
            has_alembic_table = cursor.fetchone() is not None

            has_valid_version = False
            if has_alembic_table:
                cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
                has_valid_version = cursor.fetchone() is not None

            # Check if users table exists (indicates existing database)
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            )
            has_users = cursor.fetchone() is not None

            conn.close()

            # If database has tables but no valid alembic version, run fallback first
            # to ensure all columns exist, then run idempotent migrations
            if has_users and not has_valid_version:
                print("Existing database detected without valid alembic version...")
                print("Running fallback migration to ensure schema is complete...")
                from invoicely.migrations.add_new_fields import migrate
                migrate(settings.data_dir / "invoicely.db")
        except Exception as e:
            print(f"Database check failed: {e}")

    # Run upgrade to head (migrations are idempotent - safe to run on any state)
    try:
        command.upgrade(alembic_cfg, "head")
        print("Alembic migrations completed successfully")
    except Exception as e:
        print(f"Alembic migration failed: {e}")
        # Fall back to manual migration for backwards compatibility
        from invoicely.migrations.add_new_fields import migrate
        migrate(settings.data_dir / "invoicely.db")

        # CRITICAL: Stamp database after fallback to prevent repeated failures
        try:
            command.stamp(alembic_cfg, "head")
            print("Database stamped at head after fallback migration")
        except Exception as stamp_error:
            print(f"Warning: Could not stamp database: {stamp_error}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager."""
    import sys
    print("Starting Invoice Machine...", flush=True)

    # Startup - run Alembic migrations first
    print("Running database migrations...", flush=True)
    run_alembic_migrations()
    print("Migrations complete.", flush=True)

    print("Initializing database...", flush=True)
    await init_db()
    print("Database initialized.", flush=True)

    # Rebuild FTS tables on startup (ensures search index is in sync with data)
    print("Rebuilding FTS search indexes...", flush=True)
    try:
        from invoicely.database import async_session_maker
        from invoicely.services import SearchService
        async with async_session_maker() as session:
            reindex_result = await SearchService.reindex_fts(session)
            if reindex_result.get("skipped"):
                print(f"FTS rebuild skipped: {reindex_result.get('reason', 'no data')}", flush=True)
            elif reindex_result.get("error"):
                print(f"FTS rebuild error: {reindex_result.get('error')}", flush=True)
            elif reindex_result.get("rebuilt"):
                indexed_invoices = reindex_result.get("invoices_indexed", 0)
                indexed_clients = reindex_result.get("clients_indexed", 0)
                indexed_line_items = reindex_result.get("line_items_indexed", 0)
                print(f"FTS rebuild complete: {indexed_invoices} invoices, {indexed_clients} clients, {indexed_line_items} line items indexed", flush=True)
    except Exception as e:
        print(f"FTS rebuild failed (non-fatal): {e}", flush=True)

    # Start background tasks
    print("Starting background tasks...", flush=True)
    cleanup_task = asyncio.create_task(session_cleanup_task())
    backup_task = asyncio.create_task(scheduled_backup_task())
    trash_task = asyncio.create_task(trash_cleanup_task())
    overdue_task = asyncio.create_task(overdue_check_task())
    recurring_task = asyncio.create_task(recurring_invoice_task())
    print("Background tasks started.", flush=True)

    print("Invoice Machine ready! Listening on port 8080", flush=True)
    yield

    # Shutdown
    for task in [cleanup_task, backup_task, trash_task, overdue_task, recurring_task]:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await close_db()


app = FastAPI(
    title="Invoice Machine",
    description="AI-first invoicing application",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware - configured from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"],
)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size to prevent DoS attacks."""

    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB default limit

    async def dispatch(self, request: Request, call_next):
        # Check Content-Length header if present
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.MAX_BODY_SIZE:
                    return JSONResponse(
                        {"detail": "Request body too large"},
                        status_code=413,
                    )
            except ValueError:
                pass  # Invalid content-length, let request proceed
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS protection (legacy but still useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy - don't leak full URLs to external sites
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions Policy - disable unnecessary browser features
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )

        # Content Security Policy - strict policy for API, relaxed for SPA
        if request.url.path.startswith("/api/"):
            # API endpoints: very strict CSP
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )
        # SPA pages get their CSP from the HTML meta tag

        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Protect API routes with authentication."""
    path = request.url.path

    # Allow public paths and non-API routes (MCP is mounted separately and bypasses this middleware)
    if path in PUBLIC_PATHS or not path.startswith("/api/"):
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
app.include_router(recurring.router)
app.include_router(email.router)
app.include_router(search.router)
app.include_router(analytics.router)
# Note: mcp.router is NOT included here - MCP routes are mounted separately below

# Mount MCP as a separate Starlette app to bypass BaseHTTPMiddleware (which breaks SSE streaming)
# The SSE transport needs raw ASGI access to control response streaming directly
from starlette.applications import Starlette
mcp_asgi_app = Starlette(routes=[
    Route("/sse", endpoint=mcp.mcp_sse_handler),
    Route("/messages/", endpoint=mcp.mcp_messages_handler, methods=["POST"]),
    Route("/status", endpoint=mcp.mcp_status_handler),
])
app.mount("/mcp", mcp_asgi_app)


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
