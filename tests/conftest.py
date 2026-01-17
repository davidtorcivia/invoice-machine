"""Test fixtures and configuration."""

import asyncio
import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from invoicely.database import Base, BusinessProfile, Client, Invoice, InvoiceItem, RecurringSchedule
from invoicely.services import generate_invoice_number, calculate_due_date, RecurringService, SearchService


@pytest.fixture(scope="function")
def temp_db_path():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    # Cleanup
    Path(path).unlink(missing_ok=True)


@pytest.fixture(scope="function")
async def engine(temp_db_path):
    """Create test database engine."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{temp_db_path}", echo=False)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()


@pytest.fixture(scope="function")
async def session_maker(engine):
    """Create session maker for tests."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="function")
async def db_session(session_maker):
    """Get a database session for tests."""
    async with session_maker() as session:
        yield session


@pytest.fixture
async def business_profile(db_session: AsyncSession) -> BusinessProfile:
    """Create a test business profile."""
    profile = BusinessProfile(
        id=1,
        name="Test User",
        business_name="Test Business LLC",
        email="test@example.com",
        phone="555-1234",
        address_line1="123 Main St",
        city="Test City",
        state="TS",
        postal_code="12345",
        country="United States",
        default_payment_terms_days=30,
        accent_color="#0891b2",
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile


@pytest.fixture
async def test_client(db_session: AsyncSession) -> Client:
    """Create a test client."""
    client = Client(
        name="John Doe",
        business_name="Acme Corp",
        email="john@acme.com",
        phone="555-9999",
        address_line1="456 Client St",
        city="Client City",
        state="CS",
        postal_code="54321",
        payment_terms_days=30,
    )
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client
