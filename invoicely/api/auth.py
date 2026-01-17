"""Authentication API endpoints."""

import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from invoicely.database import User, get_session
from invoicely.config import get_settings
from invoicely.rate_limit import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

# In-memory session store (for simplicity - works fine for single-instance)
# Key: session_token, Value: {"user_id": int, "expires": datetime}
_sessions: dict[str, dict] = {}

SESSION_COOKIE_NAME = "session"
SESSION_DURATION_DAYS = 30


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


def create_session(user_id: int) -> str:
    """Create a new session token."""
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "user_id": user_id,
        "expires": datetime.utcnow() + timedelta(days=SESSION_DURATION_DAYS),
    }
    return token


def get_session_user_id(token: str) -> Optional[int]:
    """Get user ID from session token if valid."""
    session = _sessions.get(token)
    if not session:
        return None
    if datetime.utcnow() > session["expires"]:
        del _sessions[token]
        return None
    return session["user_id"]


def delete_session(token: str):
    """Delete a session."""
    _sessions.pop(token, None)


def cleanup_expired_sessions():
    """Remove all expired sessions from memory."""
    now = datetime.utcnow()
    expired = [token for token, data in _sessions.items() if now > data["expires"]]
    for token in expired:
        del _sessions[token]
    return len(expired)


class AuthStatus(BaseModel):
    """Authentication status response."""
    authenticated: bool
    needs_setup: bool
    username: Optional[str] = None


class SetupRequest(BaseModel):
    """Initial setup request."""
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """Login request."""
    username: str = Field(..., max_length=100)
    password: str = Field(..., max_length=128)


@router.get("/status", response_model=AuthStatus)
async def auth_status(
    session: AsyncSession = Depends(get_session),
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
):
    """Check authentication status and if setup is needed."""
    user_count = await User.count(session)
    needs_setup = user_count == 0

    if needs_setup:
        return AuthStatus(authenticated=False, needs_setup=True)

    if not session_token:
        return AuthStatus(authenticated=False, needs_setup=False)

    user_id = get_session_user_id(session_token)
    if not user_id:
        return AuthStatus(authenticated=False, needs_setup=False)

    # Get username
    from sqlalchemy import select
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        return AuthStatus(authenticated=False, needs_setup=False)

    return AuthStatus(authenticated=True, needs_setup=False, username=user.username)


@router.post("/setup")
@limiter.limit("5/minute")
async def setup(
    request: Request,
    data: SetupRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Create initial user account (only works if no users exist)."""
    user_count = await User.count(session)
    if user_count > 0:
        raise HTTPException(status_code=400, detail="Setup already completed")

    # Normalize username to lowercase
    username = data.username.strip().lower()

    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Create user
    user = User(
        username=username,
        password_hash=hash_password(data.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    # Create session
    token = create_session(user.id)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict" if settings.secure_cookies else "lax",
        max_age=SESSION_DURATION_DAYS * 24 * 60 * 60,
    )

    return {"success": True, "username": user.username}


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    data: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Log in with username and password."""
    user = await User.get_by_username(session, data.username)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Create session
    token = create_session(user.id)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict" if settings.secure_cookies else "lax",
        max_age=SESSION_DURATION_DAYS * 24 * 60 * 60,
    )

    return {"success": True, "username": user.username}


@router.post("/logout")
async def logout(
    response: Response,
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
):
    """Log out and clear session."""
    if session_token:
        delete_session(session_token)

    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"success": True}
