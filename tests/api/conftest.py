from datetime import date
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from invoice_machine.api.auth import SESSION_COOKIE_NAME, create_session
from invoice_machine.database import Base, BusinessProfile, User
from invoice_machine.main import app


@pytest_asyncio.fixture(scope="function")
async def test_client():
    """Test client for HTTP requests with authentication."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    import invoice_machine.database

    original_maker = invoice_machine.database.async_session_maker
    invoice_machine.database.async_session_maker = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    async with invoice_machine.database.async_session_maker() as session:
        profile = BusinessProfile(
            id=1,
            name="Test Business",
            business_name="Test LLC",
            email="test@example.com",
        )
        session.add(profile)

        user = User(
            id=1,
            username="testuser",
            password_hash="test-password-hash",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    async with invoice_machine.database.async_session_maker() as session:
        user_session = await create_session(session, user.id)
        session_token = user_session.token
        csrf_token = user_session.csrf_token

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    client.cookies.set(SESSION_COOKIE_NAME, session_token)
    client.headers.update({"X-CSRF-Token": csrf_token})

    yield client
    await client.aclose()

    invoice_machine.database.async_session_maker = original_maker
    await engine.dispose()
