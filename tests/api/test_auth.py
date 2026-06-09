"""Auth endpoint flow tests: setup, login, CSRF, logout.

These exercise the real middleware + endpoint paths (password hashing, session
cookies, CSRF enforcement) against a fresh empty database — the prior suite
synthesized sessions directly and never covered these flows.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from invoice_machine.api.auth import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME
from invoice_machine.database import Base
from invoice_machine.main import app

GOOD_PASSWORD = "Test1234"


@pytest_asyncio.fixture(scope="function")
async def unauth_client():
    """An unauthenticated client backed by an empty database (no user yet)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    import invoice_machine.database

    original_maker = invoice_machine.database.async_session_maker
    invoice_machine.database.async_session_maker = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield client
    await client.aclose()

    invoice_machine.database.async_session_maker = original_maker
    await engine.dispose()


async def _setup(client, username="admin", password=GOOD_PASSWORD):
    return await client.post("/api/auth/setup", json={"username": username, "password": password})


@pytest.mark.asyncio
async def test_status_reports_needs_setup_on_empty_db(unauth_client):
    response = await unauth_client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["needs_setup"] is True
    assert data["authenticated"] is False


@pytest.mark.asyncio
async def test_setup_creates_first_user_and_authenticates(unauth_client):
    response = await _setup(unauth_client)
    assert response.status_code == 200
    assert response.json()["username"] == "admin"
    # Setup logs the user in: a subsequent status check is authenticated.
    status = await unauth_client.get("/api/auth/status")
    assert status.json()["authenticated"] is True


@pytest.mark.asyncio
async def test_setup_blocked_once_a_user_exists(unauth_client):
    assert (await _setup(unauth_client)).status_code == 200
    second = await _setup(unauth_client, username="other")
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_setup_rejects_weak_password(unauth_client):
    # Long enough to pass the schema's min_length, but no uppercase/digit so the
    # endpoint's complexity check rejects it (400, not a schema 422).
    response = await _setup(unauth_client, password="weakpassword")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_succeeds_with_correct_credentials(unauth_client):
    await _setup(unauth_client)
    unauth_client.cookies.clear()

    response = await unauth_client.post(
        "/api/auth/login", json={"username": "admin", "password": GOOD_PASSWORD}
    )
    assert response.status_code == 200
    assert SESSION_COOKIE_NAME in response.cookies


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(unauth_client):
    await _setup(unauth_client)
    unauth_client.cookies.clear()

    response = await unauth_client.post(
        "/api/auth/login", json={"username": "admin", "password": "Wrong1234"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_rejects_unknown_user(unauth_client):
    await _setup(unauth_client)
    unauth_client.cookies.clear()

    response = await unauth_client.post(
        "/api/auth/login", json={"username": "nobody", "password": GOOD_PASSWORD}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_requires_authentication(unauth_client):
    await _setup(unauth_client)
    unauth_client.cookies.clear()

    response = await unauth_client.get("/api/clients")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unsafe_method_requires_csrf_token(unauth_client):
    await _setup(unauth_client)  # leaves the session cookie set + authenticated
    csrf = unauth_client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf

    # Cookie present but no X-CSRF-Token header -> rejected.
    missing = await unauth_client.post("/api/clients", json={"name": "Acme"})
    assert missing.status_code == 403

    # Correct token -> accepted.
    ok = await unauth_client.post(
        "/api/clients", json={"name": "Acme"}, headers={"X-CSRF-Token": csrf}
    )
    assert ok.status_code in (200, 201)


@pytest.mark.asyncio
async def test_logout_invalidates_session(unauth_client):
    await _setup(unauth_client)
    csrf = unauth_client.cookies.get(CSRF_COOKIE_NAME)

    logout = await unauth_client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logout.status_code == 200

    # The session no longer authenticates protected routes.
    after = await unauth_client.get("/api/clients")
    assert after.status_code == 401
