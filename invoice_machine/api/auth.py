"""Authentication API endpoints.

Implements secure session management with:
- Database-backed sessions (persistent, scalable)
- CSRF protection via double-submit cookie pattern
- Password complexity requirements
- Rate limiting on auth endpoints
"""

import re
import secrets
import hashlib
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, Request, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import User, Session as DbSession, get_session, async_session_maker
from invoice_machine.config import get_settings
from invoice_machine.rate_limit import limiter
from invoice_machine.utils import utc_now

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

SESSION_COOKIE_NAME = "session"
CSRF_COOKIE_NAME = "csrf_token"
SESSION_DURATION_DAYS = 30

# Password complexity requirements (OWASP guidelines)
PASSWORD_MIN_LENGTH = 8
PASSWORD_REQUIREMENTS = [
    (r"[a-z]", "Password must contain at least one lowercase letter"),
    (r"[A-Z]", "Password must contain at least one uppercase letter"),
    (r"[0-9]", "Password must contain at least one digit"),
]


def validate_password_complexity(password: str) -> Optional[str]:
    """
    Validate password meets complexity requirements.

    Returns error message if invalid, None if valid.
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters"

    for pattern, message in PASSWORD_REQUIREMENTS:
        if not re.search(pattern, password):
            return message

    return None


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with random salt.

    Uses 600,000 iterations per OWASP recommendations for PBKDF2-HMAC-SHA256.
    """
    salt = secrets.token_bytes(32)
    # PBKDF2 with SHA-256, 600k iterations (OWASP recommended)
    hash_bytes = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        iterations=600_000,
        dklen=32
    )
    # Format: salt$iterations$hash (all hex encoded)
    return f"{salt.hex()}$600000${hash_bytes.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against stored hash using constant-time comparison."""
    try:
        parts = password_hash.split("$")

        # Support both old SHA-256 format and new PBKDF2 format
        if len(parts) == 2:
            # Legacy SHA-256 format: salt$hash
            salt, stored_hash = parts
            hash_obj = hashlib.sha256((salt + password).encode())
            return secrets.compare_digest(hash_obj.hexdigest(), stored_hash)
        elif len(parts) == 3:
            # New PBKDF2 format: salt$iterations$hash
            salt_hex, iterations_str, stored_hash = parts
            salt = bytes.fromhex(salt_hex)
            iterations = int(iterations_str)

            hash_bytes = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt,
                iterations=iterations,
                dklen=32
            )
            return secrets.compare_digest(hash_bytes.hex(), stored_hash)
        else:
            return False
    except (ValueError, TypeError):
        return False


async def create_session(
    db_session: AsyncSession,
    user_id: int,
    request: Optional[Request] = None,
) -> DbSession:
    """Create a new database-backed session with CSRF token.

    Args:
        db_session: Database session
        user_id: User ID to create session for
        request: Optional request for extracting user agent and IP

    Returns:
        Created Session object with token and csrf_token
    """
    expires_at = utc_now() + timedelta(days=SESSION_DURATION_DAYS)

    user_agent = None
    ip_address = None
    if request:
        user_agent = request.headers.get("user-agent", "")[:500]  # Truncate to fit
        # Get real IP, considering proxies
        ip_address = request.headers.get("x-forwarded-for", request.client.host if request.client else None)
        if ip_address and "," in ip_address:
            ip_address = ip_address.split(",")[0].strip()

    return await DbSession.create(
        db_session,
        user_id=user_id,
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address,
    )


async def get_session_data(db_session: AsyncSession, token: str) -> Optional[DbSession]:
    """Get session data from database if valid and not expired."""
    return await DbSession.get_by_token(db_session, token)


async def delete_session(db_session: AsyncSession, token: str) -> bool:
    """Delete a session from database."""
    return await DbSession.delete_by_token(db_session, token)


async def cleanup_expired_sessions(db_session: AsyncSession) -> int:
    """Remove all expired sessions from database."""
    return await DbSession.delete_expired(db_session)


async def get_session_user_id(token: str) -> Optional[int]:
    """
    Validate a session token and return the user_id if valid.

    This is a convenience wrapper that manages its own database session,
    suitable for use in middleware where no session context exists.

    Args:
        token: The session token to validate

    Returns:
        The user_id if session is valid, None otherwise
    """
    async with async_session_maker() as db_session:
        session = await get_session_data(db_session, token)
        if session and session.user_id:
            return session.user_id
        return None


async def run_session_cleanup() -> int:
    """
    Run session cleanup with its own database session.

    This is a convenience wrapper for use in background tasks.

    Returns:
        Number of sessions deleted
    """
    async with async_session_maker() as db_session:
        count = await cleanup_expired_sessions(db_session)
        await db_session.commit()
        return count


class AuthStatus(BaseModel):
    """Authentication status response."""

    authenticated: bool
    needs_setup: bool
    username: Optional[str] = None
    csrf_token: Optional[str] = None  # Included for authenticated users


class SetupRequest(BaseModel):
    """Initial setup request."""

    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """Login request."""

    username: str = Field(..., max_length=100)
    password: str = Field(..., max_length=128)


def _set_session_cookies(response: Response, session: DbSession) -> None:
    """Set both session and CSRF cookies."""
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session.token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict" if settings.secure_cookies else "lax",
        max_age=SESSION_DURATION_DAYS * 24 * 60 * 60,
    )
    # CSRF token cookie - readable by JavaScript for header submission
    response.set_cookie(
        CSRF_COOKIE_NAME,
        session.csrf_token,
        httponly=False,  # JavaScript needs to read this
        secure=settings.secure_cookies,
        samesite="strict" if settings.secure_cookies else "lax",
        max_age=SESSION_DURATION_DAYS * 24 * 60 * 60,
    )


async def verify_csrf_token(
    db_session: AsyncSession,
    session_token: str,
    csrf_header: Optional[str],
) -> bool:
    """
    Verify CSRF token matches the session's token.

    Uses double-submit cookie pattern: client must send CSRF token
    in X-CSRF-Token header that matches the session's csrf_token.
    """
    if not csrf_header:
        return False

    session = await get_session_data(db_session, session_token)
    if not session:
        return False

    return secrets.compare_digest(session.csrf_token, csrf_header)


@router.get("/status", response_model=AuthStatus)
async def auth_status(
    db_session: AsyncSession = Depends(get_session),
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
):
    """Check authentication status and if setup is needed."""
    user_count = await User.count(db_session)
    needs_setup = user_count == 0

    if needs_setup:
        return AuthStatus(authenticated=False, needs_setup=True)

    if not session_token:
        return AuthStatus(authenticated=False, needs_setup=False)

    # Get session from database
    user_session = await get_session_data(db_session, session_token)
    if not user_session:
        return AuthStatus(authenticated=False, needs_setup=False)

    # Get username from the session's user relationship
    user = user_session.user
    if not user:
        return AuthStatus(authenticated=False, needs_setup=False)

    return AuthStatus(
        authenticated=True,
        needs_setup=False,
        username=user.username,
        csrf_token=user_session.csrf_token,
    )


@router.post("/setup")
@limiter.limit("3/minute")  # Reduced from 5/min for security
async def setup(
    request: Request,
    data: SetupRequest,
    response: Response,
    db_session: AsyncSession = Depends(get_session),
):
    """Create initial user account (only works if no users exist)."""
    user_count = await User.count(db_session)
    if user_count > 0:
        raise HTTPException(status_code=400, detail="Setup already completed")

    # Normalize username to lowercase
    username = data.username.strip().lower()

    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")

    # Validate password complexity
    password_error = validate_password_complexity(data.password)
    if password_error:
        raise HTTPException(status_code=400, detail=password_error)

    # Create user
    user = User(
        username=username,
        password_hash=hash_password(data.password),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Create database-backed session with CSRF token
    user_session = await create_session(db_session, user.id, request)
    _set_session_cookies(response, user_session)

    return {"success": True, "username": user.username}


@router.post("/login")
@limiter.limit("3/minute")  # Reduced from 5/min for security
async def login(
    request: Request,
    data: LoginRequest,
    response: Response,
    db_session: AsyncSession = Depends(get_session),
):
    """Log in with username and password."""
    user = await User.get_by_username(db_session, data.username)
    if not user or not verify_password(data.password, user.password_hash):
        # Use generic error message to prevent username enumeration
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Create database-backed session with CSRF token
    user_session = await create_session(db_session, user.id, request)
    _set_session_cookies(response, user_session)

    return {"success": True, "username": user.username}


@router.post("/logout")
async def logout(
    response: Response,
    db_session: AsyncSession = Depends(get_session),
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
):
    """Log out and clear session from database."""
    if session_token:
        await delete_session(db_session, session_token)

    response.delete_cookie(SESSION_COOKIE_NAME)
    response.delete_cookie(CSRF_COOKIE_NAME)
    return {"success": True}
