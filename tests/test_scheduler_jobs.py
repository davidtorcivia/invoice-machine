"""Run the app_runtime lifespan jobs against a temp DB and assert their effects."""

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


def test_seconds_until_next_hour_is_at_most_one_hour():
    secs = app_runtime._seconds_until_next_hour()
    assert 1 <= secs <= 3600


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

    await app_runtime._scheduled_backup_job()


@pytest.mark.asyncio
async def test_backup_service_builder_decrypts_s3_credentials(scheduler_db):
    """The shared builder must decrypt the stored (Fernet-encrypted) S3 credentials."""
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


@pytest.fixture
def stub_lifespan(monkeypatch, tmp_path):
    """Neutralize everything the lifespan touches except the scheduler gating."""
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    @asynccontextmanager
    async def fake_mcp_lifespan():
        yield

    monkeypatch.setattr(app_runtime, "ensure_database_schema", AsyncMock())
    monkeypatch.setattr(app_runtime, "_rebuild_search_indexes", AsyncMock())
    monkeypatch.setattr(app_runtime, "close_db", AsyncMock())
    monkeypatch.setattr(app_runtime, "streamable_http_lifespan", fake_mcp_lifespan)
    monkeypatch.setattr(app_runtime, "settings", SimpleNamespace(data_dir=tmp_path, port=8080))

    jobs = {
        name: AsyncMock()
        for name in ("_overdue_check_job", "_recurring_invoice_job", "_payment_reminder_job")
    }
    for name, job in jobs.items():
        monkeypatch.setattr(app_runtime, name, job)
    return SimpleNamespace(jobs=jobs, app=MagicMock())


@pytest.mark.asyncio
async def test_startup_catch_up_jobs_run_when_the_lock_is_held(stub_lifespan, monkeypatch):
    monkeypatch.setattr(app_runtime, "_acquire_scheduler_lock", lambda: object())

    async with app_runtime.lifespan(stub_lifespan.app):
        pass

    assert all(job.await_count == 1 for job in stub_lifespan.jobs.values())


@pytest.mark.asyncio
async def test_startup_catch_up_jobs_are_skipped_without_the_lock(stub_lifespan, monkeypatch):
    """A second worker must not generate recurring invoices at boot."""
    monkeypatch.setattr(app_runtime, "_acquire_scheduler_lock", lambda: None)

    async with app_runtime.lifespan(stub_lifespan.app):
        pass

    assert all(job.await_count == 0 for job in stub_lifespan.jobs.values())


@pytest.mark.asyncio
async def test_a_failing_catch_up_job_does_not_block_startup(stub_lifespan, monkeypatch):
    monkeypatch.setattr(app_runtime, "_acquire_scheduler_lock", lambda: object())
    stub_lifespan.jobs["_overdue_check_job"].side_effect = RuntimeError("boom")

    async with app_runtime.lifespan(stub_lifespan.app):
        pass

    assert stub_lifespan.jobs["_recurring_invoice_job"].await_count == 1


def test_scheduler_lock_is_refused_while_another_holder_has_it(monkeypatch, tmp_path):
    from types import SimpleNamespace

    monkeypatch.setattr(app_runtime, "settings", SimpleNamespace(data_dir=tmp_path))
    first = app_runtime._acquire_scheduler_lock()
    assert first is not None

    try:
        assert app_runtime._acquire_scheduler_lock() is None
    finally:
        first.close()


@pytest.mark.asyncio
async def test_wait_out_restore_returns_once_the_restore_clears(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    app = SimpleNamespace(state=SimpleNamespace(restore_in_progress=True))
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)
        app.state.restore_in_progress = False

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    await app_runtime._wait_out_restore(app)

    assert slept == [app_runtime._RESTORE_WAIT_SECONDS]


@pytest.mark.asyncio
@pytest.mark.parametrize("runner", ["_run_hourly_task", "_run_daily_task"])
async def test_periodic_runners_survive_a_failing_job(monkeypatch, runner):
    """A job that raises is logged, and the loop keeps running."""
    import asyncio
    from types import SimpleNamespace

    monkeypatch.setattr(app_runtime, "_seconds_until_next_hour", lambda: 0)
    monkeypatch.setattr(app_runtime, "_seconds_until_hour", lambda hour: 0)
    app = SimpleNamespace(state=SimpleNamespace(restore_in_progress=False, jobs={}))
    calls = []

    async def job():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("first run explodes")

    args = (app, "job", job) if runner == "_run_hourly_task" else (app, 3, "job", job)
    task = asyncio.create_task(getattr(app_runtime, runner)(*args))
    while len(calls) < 2:
        await asyncio.sleep(0)
    task.cancel()

    assert len(calls) >= 2
    assert app.state.jobs["job"]["failures"] == 1
    assert app.state.jobs["job"]["runs"] >= 2


@pytest.mark.asyncio
async def test_session_cleanup_job_runs(scheduler_db):
    await app_runtime._session_cleanup_job()


@pytest.mark.asyncio
async def test_trash_cleanup_job_purges_expired_trash(scheduler_db):
    from invoice_machine.database import Client

    async with scheduler_db() as session:
        client = Client(name="Gone Co", deleted_at=utc_now() - timedelta(days=400))
        session.add(client)
        await session.commit()
        client_id = client.id

    await app_runtime._trash_cleanup_job()

    async with scheduler_db() as session:
        assert await session.get(Client, client_id) is None


@pytest.mark.asyncio
async def test_reminder_job_sends_at_the_local_send_hour(scheduler_db, monkeypatch):
    from unittest.mock import AsyncMock

    from invoice_machine.database import BusinessProfile

    async with scheduler_db() as session:
        profile = await BusinessProfile.get_or_create(session)
        profile.reminders_enabled = 1
        profile.reminder_send_hour = 9
        await session.commit()

    sender = AsyncMock(return_value=[{"success": True}, {"success": False}])
    monkeypatch.setattr("invoice_machine.service.reminders.send_due_reminders", sender)
    monkeypatch.setattr(
        "invoice_machine.service.reminders.business_now",
        lambda profile: utc_now().replace(hour=9),
    )

    await app_runtime._payment_reminder_job()

    assert sender.await_count == 1


@pytest.mark.asyncio
async def test_reminder_job_waits_for_the_send_hour(scheduler_db, monkeypatch):
    from unittest.mock import AsyncMock

    from invoice_machine.database import BusinessProfile

    async with scheduler_db() as session:
        profile = await BusinessProfile.get_or_create(session)
        profile.reminders_enabled = 1
        profile.reminder_send_hour = 9
        await session.commit()

    sender = AsyncMock(return_value=[])
    monkeypatch.setattr("invoice_machine.service.reminders.send_due_reminders", sender)
    monkeypatch.setattr(
        "invoice_machine.service.reminders.business_now",
        lambda profile: utc_now().replace(hour=10),
    )

    await app_runtime._payment_reminder_job()

    assert sender.await_count == 0


@pytest.mark.asyncio
async def test_reminder_job_noops_when_reminders_are_disabled(scheduler_db):
    from invoice_machine.database import BusinessProfile

    async with scheduler_db() as session:
        profile = await BusinessProfile.get_or_create(session)
        profile.reminders_enabled = 0
        await session.commit()

    await app_runtime._payment_reminder_job()


@pytest.mark.asyncio
async def test_scheduled_backup_job_reports_a_failed_s3_upload(scheduler_db, monkeypatch, caplog):
    from unittest.mock import AsyncMock, MagicMock

    from invoice_machine.database import BusinessProfile

    async with scheduler_db() as session:
        profile = await BusinessProfile.get_or_create(session)
        profile.backup_enabled = 1
        await session.commit()

    service = MagicMock()
    service.create_backup.return_value = {"filename": "b.db.gz", "s3_error": "bucket missing"}
    monkeypatch.setattr(
        "invoice_machine.api.backup.get_backup_service", AsyncMock(return_value=service)
    )

    with caplog.at_level("ERROR"):
        await app_runtime._scheduled_backup_job()

    assert "bucket missing" in caplog.text
    assert service.cleanup_old_backups.called


@pytest.mark.asyncio
async def test_scheduled_backup_job_logs_success(scheduler_db, monkeypatch, caplog):
    from unittest.mock import AsyncMock, MagicMock

    from invoice_machine.database import BusinessProfile

    async with scheduler_db() as session:
        profile = await BusinessProfile.get_or_create(session)
        profile.backup_enabled = 1
        await session.commit()

    service = MagicMock()
    service.create_backup.return_value = {"filename": "backup.db.gz"}
    monkeypatch.setattr(
        "invoice_machine.api.backup.get_backup_service", AsyncMock(return_value=service)
    )

    with caplog.at_level("INFO"):
        await app_runtime._scheduled_backup_job()

    assert "backup.db.gz" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reindex_result,expected",
    [
        ({"skipped": True, "reason": "no data"}, "no data"),
        ({"error": "fts missing"}, "fts missing"),
        ({"rebuilt": True, "invoices_indexed": 2}, "FTS rebuild complete"),
    ],
)
async def test_rebuild_search_indexes_reports_each_outcome(
    scheduler_db, monkeypatch, caplog, reindex_result, expected
):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "invoice_machine.services.SearchService.reindex_fts", AsyncMock(return_value=reindex_result)
    )

    with caplog.at_level("INFO"):
        await app_runtime._rebuild_search_indexes()

    assert expected in caplog.text
