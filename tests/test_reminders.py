"""Automated payment reminder behavior."""

import json
from datetime import UTC, date, datetime

import pytest

from invoice_machine.database import Invoice, ReminderDelivery
from invoice_machine.service.reminders import ReminderService


@pytest.fixture
async def reminder_invoice(db_session, test_client):
    invoice = Invoice(
        invoice_number="REM-1",
        client_id=test_client.id,
        client_name=test_client.name,
        client_email=test_client.email,
        issue_date=date(2026, 1, 1),
        due_date=date(2026, 1, 10),
        currency_code="USD",
        subtotal=100,
        total=100,
        status="overdue",
        reminders_enabled=1,
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)
    return invoice


async def _enable_reminders(business_profile):
    business_profile.reminders_enabled = 1
    business_profile.reminder_offsets = json.dumps([-3, 0, 3, 7])
    business_profile.business_timezone = "UTC"
    business_profile.reminder_send_hour = 9
    business_profile.smtp_enabled = 1


@pytest.mark.asyncio
async def test_reminders_are_disabled_by_default(
    db_session, business_profile, reminder_invoice
):
    assert await ReminderService.process_due_reminders(
        db_session, now=datetime(2026, 1, 13, 10, tzinfo=UTC)
    ) == []


@pytest.mark.asyncio
async def test_due_reminder_is_sent_once(
    db_session, business_profile, reminder_invoice, monkeypatch
):
    await _enable_reminders(business_profile)
    await db_session.commit()
    calls = []

    async def fake_send(session, invoice_id, **kwargs):
        calls.append((invoice_id, kwargs))
        return {"success": True}

    monkeypatch.setattr("invoice_machine.service.reminders.send_invoice_email", fake_send)
    now = datetime(2026, 1, 13, 10, tzinfo=UTC)
    first = await ReminderService.process_due_reminders(db_session, now=now)
    second = await ReminderService.process_due_reminders(db_session, now=now)

    assert first[0]["status"] == "sent"
    assert first[0]["offset_days"] == 3
    assert second == []
    assert len(calls) == 1
    assert "REM-1" in calls[0][1]["subject"]


@pytest.mark.asyncio
async def test_downtime_catchup_sends_only_latest_eligible_reminder(
    db_session, business_profile, reminder_invoice, monkeypatch
):
    await _enable_reminders(business_profile)
    await db_session.commit()

    async def fake_send(*args, **kwargs):
        return {"success": True}

    monkeypatch.setattr("invoice_machine.service.reminders.send_invoice_email", fake_send)
    result = await ReminderService.process_due_reminders(
        db_session, now=datetime(2026, 1, 11, 10, tzinfo=UTC)
    )
    assert [item["offset_days"] for item in result] == [0]


@pytest.mark.asyncio
async def test_paid_invoice_never_receives_reminder(
    db_session, business_profile, reminder_invoice, monkeypatch
):
    await _enable_reminders(business_profile)
    reminder_invoice.status = "paid"
    await db_session.commit()
    called = False

    async def fake_send(*args, **kwargs):
        nonlocal called
        called = True
        return {"success": True}

    monkeypatch.setattr("invoice_machine.service.reminders.send_invoice_email", fake_send)
    assert await ReminderService.process_due_reminders(
        db_session, now=datetime(2026, 1, 13, 10, tzinfo=UTC)
    ) == []
    assert called is False


@pytest.mark.asyncio
async def test_failed_reminder_can_retry_without_duplicate_delivery(
    db_session, business_profile, reminder_invoice, monkeypatch
):
    await _enable_reminders(business_profile)
    await db_session.commit()
    attempts = 0

    async def flaky_send(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        return {"success": attempts == 2, "error": "Temporary SMTP failure"}

    monkeypatch.setattr("invoice_machine.service.reminders.send_invoice_email", flaky_send)
    now = datetime(2026, 1, 13, 10, tzinfo=UTC)
    first = await ReminderService.process_due_reminders(db_session, now=now)
    second = await ReminderService.process_due_reminders(db_session, now=now)
    deliveries = await ReminderService.list_deliveries(db_session, reminder_invoice.id)

    assert first[0]["status"] == "failed"
    assert second[0]["status"] == "sent"
    assert attempts == 2
    assert len(deliveries) == 1


@pytest.mark.asyncio
async def test_abandoned_reminder_claim_is_retried(
    db_session, business_profile, reminder_invoice, monkeypatch
):
    await _enable_reminders(business_profile)
    claimed_at = datetime(2026, 1, 13, 9, 30, tzinfo=UTC)
    db_session.add(
        ReminderDelivery(
            invoice_id=reminder_invoice.id,
            due_date=reminder_invoice.due_date,
            offset_days=3,
            recipient=reminder_invoice.client_email,
            status="sending",
            claimed_at=claimed_at,
        )
    )
    await db_session.commit()
    calls = 0

    async def fake_send(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {"success": True}

    monkeypatch.setattr("invoice_machine.service.reminders.send_invoice_email", fake_send)
    result = await ReminderService.process_due_reminders(
        db_session, now=datetime(2026, 1, 13, 10, tzinfo=UTC)
    )

    assert result[0]["status"] == "sent"
    assert calls == 1


@pytest.mark.asyncio
async def test_active_reminder_claim_is_not_reacquired(
    db_session, business_profile, reminder_invoice, monkeypatch
):
    await _enable_reminders(business_profile)
    now = datetime(2026, 1, 13, 10, tzinfo=UTC)
    db_session.add(
        ReminderDelivery(
            invoice_id=reminder_invoice.id,
            due_date=reminder_invoice.due_date,
            offset_days=3,
            recipient=reminder_invoice.client_email,
            status="sending",
            claimed_at=now,
        )
    )
    await db_session.commit()
    called = False

    async def fake_send(*args, **kwargs):
        nonlocal called
        called = True
        return {"success": True}

    monkeypatch.setattr("invoice_machine.service.reminders.send_invoice_email", fake_send)

    assert await ReminderService.process_due_reminders(db_session, now=now) == []
    assert called is False


def test_reminder_validation():
    assert ReminderService.parse_offsets([7, -3, 0, 7]) == [-3, 0, 7]
    assert ReminderService.validate_timezone("America/New_York") == "America/New_York"
    with pytest.raises(ValueError, match="Unknown timezone"):
        ReminderService.validate_timezone("Mars/Olympus_Mons")
