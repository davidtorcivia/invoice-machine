"""Background scheduler-job tests.

The lifespan jobs in app_runtime were untested, yet two of the 2026-06-09 audit
bugs lived here (the encrypted-S3-credential backup and the recurring-rollback
crash). These run the job functions against a temp DB and assert their effects.
"""

import json
from datetime import timedelta

import pytest
import pytest_asyncio

from invoice_machine import app_runtime
from invoice_machine.utils import utc_now


@pytest_asyncio.fixture(scope="function")
async def scheduler_db():
    """Point the scheduler jobs (which open their own sessions) at a temp DB."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    import invoice_machine.database as db
    from invoice_machine.database import Base, register_sqlite_pragmas

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    register_sqlite_pragmas(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    original_maker = db.async_session_maker
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    db.async_session_maker = maker

    yield maker

    db.async_session_maker = original_maker
    await engine.dispose()


def test_seconds_until_hour_is_within_a_day():
    secs = app_runtime._seconds_until_hour(0)
    assert 0 < secs <= 86400


@pytest.mark.asyncio
async def test_overdue_job_marks_past_due_sent_invoices(scheduler_db):
    from invoice_machine.database import Client
    from invoice_machine.services import InvoiceService

    today = utc_now().date()
    async with scheduler_db() as session:
        client = Client(name="Overdue Co")
        session.add(client)
        await session.commit()
        await session.refresh(client)

        invoice = await InvoiceService.create_invoice(
            session,
            client_id=client.id,
            issue_date=today - timedelta(days=40),
            due_date=today - timedelta(days=10),
            items=[{"description": "x", "quantity": 1, "unit_price": 100}],
        )
        await InvoiceService.update_invoice(session, invoice.id, status="sent")
        invoice_id = invoice.id

    await app_runtime._overdue_check_job()

    async with scheduler_db() as session:
        refreshed = await InvoiceService.get_invoice(session, invoice_id)
        assert refreshed.status == "overdue"


@pytest.mark.asyncio
async def test_recurring_job_generates_due_invoice(scheduler_db):
    from invoice_machine.database import Client
    from invoice_machine.services import InvoiceService, RecurringService

    async with scheduler_db() as session:
        client = Client(name="Retainer Co")
        session.add(client)
        await session.commit()
        await session.refresh(client)

        await RecurringService.create_schedule(
            session,
            client_id=client.id,
            name="Monthly",
            frequency="monthly",
            schedule_day=1,
            next_invoice_date=utc_now().date() - timedelta(days=1),
            line_items=[{"description": "Retainer", "quantity": 1, "unit_price": "500"}],
        )
        client_id = client.id

    await app_runtime._recurring_invoice_job()

    async with scheduler_db() as session:
        invoices = await InvoiceService.list_invoices(session, client_id=client_id)
        assert len(invoices) >= 1


@pytest.mark.asyncio
async def test_scheduled_backup_job_noops_when_disabled(scheduler_db):
    from invoice_machine.database import BusinessProfile

    async with scheduler_db() as session:
        profile = await BusinessProfile.get_or_create(session)
        profile.backup_enabled = 0
        await session.commit()

    # Must return cleanly without touching the filesystem.
    await app_runtime._scheduled_backup_job()


@pytest.mark.asyncio
async def test_backup_service_builder_decrypts_s3_credentials(scheduler_db):
    """Regression for the nightly-backup bug: the shared builder must decrypt the
    stored (Fernet-encrypted) S3 credentials, not pass them through raw."""
    from invoice_machine.api.backup import get_backup_service
    from invoice_machine.crypto import encrypt_credential
    from invoice_machine.database import BusinessProfile

    async with scheduler_db() as session:
        profile = await BusinessProfile.get_or_create(session)
        profile.backup_s3_enabled = 1
        profile.backup_s3_config = json.dumps(
            {
                "endpoint_url": "https://s3.example.com",
                "bucket": "backups",
                "access_key_id": encrypt_credential("AKIAPLAINTEXT"),
                "secret_access_key": encrypt_credential("secret-plaintext"),
            }
        )
        await session.commit()

        service = await get_backup_service(session)

    assert service.s3_config["access_key_id"] == "AKIAPLAINTEXT"
    assert service.s3_config["secret_access_key"] == "secret-plaintext"
    assert service.s3_config["enabled"] is True
