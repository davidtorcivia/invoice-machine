"""FastAPI application entry point."""

import asyncio
import logging
import secrets
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

from invoice_machine.config import get_settings
from invoice_machine.rate_limit import limiter
from invoice_machine.database import init_db, close_db
from invoice_machine.utils import utc_now
from starlette.routing import Route
from invoice_machine.api import profile, clients, invoices, trash, auth, mcp, backup, recurring, email, email_templates, search, analytics
from invoice_machine.api.auth import get_session_data, SESSION_COOKIE_NAME, run_session_cleanup

settings = get_settings()
STATIC_DIR = Path("invoice_machine/static")
STATIC_DIR_RESOLVED = STATIC_DIR.resolve()

# Paths that don't require authentication
PUBLIC_PATHS = {"/health", "/api/auth/status", "/api/auth/setup", "/api/auth/login"}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
def build_spa_csp_policy(request: Request) -> str:
    """Build CSP policy for non-API routes.

    Keeps strict defaults, but relaxes script/connect sources for Cloudflare-
    proxied requests so Rocket Loader/Insights don't break frontend boot.
    """
    script_src = ["'self'"]
    connect_src = ["'self'"]

    # Cloudflare proxy headers are present when traffic passes through CF.
    if request.headers.get("cf-ray") or request.headers.get("cf-visitor"):
        script_src.extend(["'unsafe-inline'", "https://static.cloudflareinsights.com"])
        connect_src.extend(
            [
                "https://cloudflareinsights.com",
                "https://*.cloudflareinsights.com",
                "https://static.cloudflareinsights.com",
            ]
        )

    policy = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' https://fonts.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        f"script-src {' '.join(script_src)}; "
        "script-src-attr 'none'; "
        f"connect-src {' '.join(connect_src)}; "
        "worker-src 'self'; "
        "manifest-src 'self'"
    )

    if settings.environment.lower() == "production":
        policy += "; upgrade-insecure-requests"

    return policy


async def session_cleanup_task():
    """Background task to cleanup expired sessions every hour."""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        await run_session_cleanup()


async def scheduled_backup_task():
    """Background task to run daily backups at midnight UTC."""
    from datetime import timedelta
    import json
    from invoice_machine.database import async_session_maker, BusinessProfile
    from invoice_machine.services import BackupService

    while True:
        # Calculate seconds until next midnight UTC
        now = utc_now()
        next_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        seconds_until_midnight = (next_midnight - now).total_seconds()

        await asyncio.sleep(seconds_until_midnight)

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


async def trash_cleanup_task():
    """Background task to auto-purge expired trash items daily at 3 AM UTC."""
    from datetime import timedelta
    from invoice_machine.tasks.cleanup_trash import cleanup_trash

    while True:
        # Calculate seconds until next 3 AM UTC
        now = utc_now()
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
    from datetime import timedelta
    from invoice_machine.database import async_session_maker
    from invoice_machine.services import InvoiceService

    while True:
        # Calculate seconds until next 1 AM UTC
        now = utc_now()
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
    from datetime import timedelta
    from invoice_machine.database import async_session_maker
    from invoice_machine.services import RecurringService

    while True:
        # Calculate seconds until next 2 AM UTC
        now = utc_now()
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

        # Backups run in scheduled_backup_task


def run_alembic_migrations():
    """Run Alembic migrations to upgrade database schema."""
    from alembic.config import Config
    from alembic import command
    from pathlib import Path
    import sqlite3

    # Mapping of old revision IDs (from invoicely) to new ones (invoice_machine)
    # This handles database migrations from the renamed package
    OLD_TO_NEW_REVISIONS = {
        "007_add_default_currency": "007_default_currency",
        "008_add_line_items_fts": "008_line_items_fts",
        "009_add_sessions": "009_recurring_enhancements",  # ID changed
    }

    # Get the alembic.ini path relative to project root
    project_root = Path(__file__).parent.parent
    alembic_cfg = Config(str(project_root / "alembic.ini"))

    # Check if database exists and has tables but no valid alembic version
    db_path = settings.data_dir / "invoice_machine.db"
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
            current_version = None
            if has_alembic_table:
                cursor.execute("SELECT version_num FROM alembic_version LIMIT 1")
                row = cursor.fetchone()
                if row:
                    has_valid_version = True
                    current_version = row[0]

            # Update old revision IDs to new ones
            if current_version and current_version in OLD_TO_NEW_REVISIONS:
                new_version = OLD_TO_NEW_REVISIONS[current_version]
                print(f"Updating alembic version from {current_version} to {new_version}...")
                cursor.execute(
                    "UPDATE alembic_version SET version_num = ?",
                    (new_version,)
                )
                conn.commit()
                print(f"Alembic version updated successfully")

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
                from invoice_machine.migrations.add_new_fields import migrate
                migrate(settings.data_dir / "invoice_machine.db")
        except Exception as e:
            print(f"Database check failed: {e}")

    # Run upgrade to head (migrations are idempotent - safe to run on any state)
    try:
        command.upgrade(alembic_cfg, "head")
        print("Alembic migrations completed successfully")
    except Exception as e:
        print(f"Alembic migration failed: {e}")
        # Fall back to manual migration for backwards compatibility
        from invoice_machine.migrations.add_new_fields import migrate
        migrate(settings.data_dir / "invoice_machine.db")

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
        from invoice_machine.database import async_session_maker
        from invoice_machine.services import SearchService
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
        else:
            response.headers["Content-Security-Policy"] = build_spa_csp_policy(request)

        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)


def _extract_bearer_token(request: Request) -> str | None:
    """Extract bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:].strip()
    return token or None


async def _verify_bot_api_key(token: str | None) -> bool:
    """Verify bot API key for bearer token authentication."""
    if not token:
        return False

    from invoice_machine.crypto import verify_api_key
    from invoice_machine.database import BusinessProfile, async_session_maker

    async with async_session_maker() as db_session:
        profile = await BusinessProfile.get(db_session)
        if not profile or not profile.bot_api_key:
            return False
        return verify_api_key(token, profile.bot_api_key)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Protect API routes with authentication."""
    path = request.url.path

    # Allow public paths and non-API routes (MCP is mounted separately and bypasses this middleware)
    if path in PUBLIC_PATHS or not path.startswith("/api/"):
        return await call_next(request)

    if request.method == "OPTIONS":
        return await call_next(request)

    # Allow bearer token authentication for bot automation on API routes
    # (excluding auth endpoints which are session-based).
    if not path.startswith("/api/auth/"):
        bearer_token = _extract_bearer_token(request)
        if await _verify_bot_api_key(bearer_token):
            return await call_next(request)

    # Check session cookie
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        return JSONResponse(
            {"detail": "Authentication required"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    from invoice_machine.database import async_session_maker
    async with async_session_maker() as db_session:
        user_session = await get_session_data(db_session, session_token)
        if not user_session or not user_session.user_id:
            return JSONResponse(
                {"detail": "Session expired"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        if request.method in UNSAFE_METHODS:
            csrf_header = request.headers.get("X-CSRF-Token")
            if not csrf_header or not secrets.compare_digest(
                user_session.csrf_token, csrf_header
            ):
                return JSONResponse(
                    {"detail": "Invalid CSRF token"},
                    status_code=status.HTTP_403_FORBIDDEN,
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
app.include_router(email_templates.router)
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


@app.get("/SKILL.md", include_in_schema=False)
async def skill_manifest(request: Request):
    """Serve a basic skill manifest for bot integrations."""
    base_url = str(request.base_url).rstrip("/")
    content = f"""# Invoice Machine Bot Skill

Use this skill to automate Invoice Machine over HTTP.

## Auth
- Header: `Authorization: Bearer <BOT_API_KEY>`
- Use the Bot API Key from the Settings page.

## Base URL
- `{base_url}/api`

## Common Endpoints
- `GET /api/profile`
- `GET /api/invoices/paginated?page=1&per_page=25`
- `POST /api/invoices`
- `PUT /api/invoices/{{id}}`
- `POST /api/clients`

## Example
```bash
curl -H "Authorization: Bearer $BOT_API_KEY" \\
  "{base_url}/api/invoices/paginated?page=1&per_page=10"
```
"""
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
