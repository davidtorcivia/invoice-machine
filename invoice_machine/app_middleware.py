"""Middleware and request guards for the FastAPI application."""

from __future__ import annotations

import logging
import secrets

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware

from invoice_machine.api.auth import SESSION_COOKIE_NAME, get_session_data
from invoice_machine.config import get_settings
from invoice_machine.rate_limit import bearer_auth_throttle, get_client_ip, limiter

settings = get_settings()
logger = logging.getLogger(__name__)
PUBLIC_PATHS = {"/health", "/api/auth/status", "/api/auth/setup", "/api/auth/login"}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def build_spa_csp_policy(request: Request) -> str:
    """Build the SPA CSP policy, with Cloudflare allowances when applicable."""
    script_src = ["'self'"]
    connect_src = ["'self'"]

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


class RequestSizeExceeded(Exception):
    """Raised when a request body exceeds the configured limit."""


class RequestSizeLimitMiddleware:
    """Limit request body size to prevent DoS attacks."""

    def __init__(self, app, max_body_size: int = 10 * 1024 * 1024):
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_body_size:
                    response = JSONResponse({"detail": "Request body too large"}, status_code=413)
                    await response(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_size:
                    raise RequestSizeExceeded()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestSizeExceeded:
            response = JSONResponse({"detail": "Request body too large"}, status_code=413)
            await response(scope, receive, send)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
            if request.url.path.startswith("/api/")
            else build_spa_csp_policy(request)
        )
        return response


def _extract_bearer_token(request: Request) -> str | None:
    """Extract bearer token from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:].strip()
    return token or None


async def _verify_bot_api_key(token: str | None) -> bool:
    """Verify bot API key for bearer-token authentication."""
    if not token:
        return False

    from invoice_machine.crypto import verify_api_key
    from invoice_machine.database import BusinessProfile, async_session_maker

    async with async_session_maker() as db_session:
        profile = await BusinessProfile.get(db_session)
        if not profile or not profile.bot_api_key:
            return False
        return verify_api_key(token, profile.bot_api_key)


def configure_http_middleware(app: FastAPI) -> None:
    """Attach shared middleware and request guards to the app."""
    # In production, warn loudly if the app's own origin isn't in the CORS
    # allow-list — a common misconfiguration (e.g. the invoice/invoices typo).
    if settings.environment.lower() == "production":
        origins = settings.cors_origins_list
        base = settings.app_base_url.rstrip("/")
        if base and base not in origins:
            logger.warning(
                "CORS_ORIGINS (%s) does not include APP_BASE_URL (%s); "
                "cross-origin browser requests from the app will be blocked.",
                origins,
                base,
            )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "Accept",
            "X-Requested-With",
            "X-CSRF-Token",
        ],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)

    @app.middleware("http")
    async def restore_guard_middleware(request: Request, call_next):
        app_state = app.state

        if getattr(app_state, "restore_in_progress", False) and request.url.path != "/health":
            return JSONResponse(
                {"detail": "Service temporarily unavailable during backup restore"},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        app_state.active_requests = getattr(app_state, "active_requests", 0) + 1
        try:
            return await call_next(request)
        finally:
            app_state.active_requests = max(0, getattr(app_state, "active_requests", 0) - 1)

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path

        if path in PUBLIC_PATHS or not path.startswith("/api/"):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        if not path.startswith("/api/auth/"):
            bearer_token = _extract_bearer_token(request)
            if bearer_token:
                client_ip = get_client_ip(request)
                if bearer_auth_throttle.is_blocked(client_ip):
                    return JSONResponse(
                        {"detail": "Too many authentication attempts. Try again later."},
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    )
                if await _verify_bot_api_key(bearer_token):
                    return await call_next(request)
                # Invalid bearer token: count it before falling back to cookie auth.
                bearer_auth_throttle.record_failure(client_ip)

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
