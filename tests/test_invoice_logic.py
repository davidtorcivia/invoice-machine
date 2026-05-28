"""Tests for invoice numbering, custom numbers, quote conversion, and recurring catch-up."""

from datetime import UTC, date, datetime

import pytest

from invoice_machine.services import InvoiceService, RecurringService


def _fixed_now(year, month, day):
    def _now():
        return datetime(year, month, day, 12, 0, tzinfo=UTC)

    return _now


def _items():
    return [{"description": "Work", "quantity": 1, "unit_price": "100"}]


@pytest.mark.asyncio
async def test_auto_number_regenerated_on_date_change(db_session, test_client):
    inv = await InvoiceService.create_invoice(
        db_session, client_id=test_client.id, issue_date=date(2026, 1, 1), items=_items()
    )
    assert inv.invoice_number == "20260101-1"

    updated = await InvoiceService.update_invoice(db_session, inv.id, issue_date=date(2026, 2, 2))
    assert updated.invoice_number == "20260202-1"


@pytest.mark.asyncio
async def test_custom_number_preserved_on_date_change(db_session, test_client):
    inv = await InvoiceService.create_invoice(
        db_session,
        client_id=test_client.id,
        issue_date=date(2026, 1, 1),
        invoice_number_override="INV-ACME-007",
        items=_items(),
    )
    assert inv.invoice_number == "INV-ACME-007"

    # Changing the date must NOT clobber a manually-assigned number.
    updated = await InvoiceService.update_invoice(db_session, inv.id, issue_date=date(2026, 3, 3))
    assert updated.invoice_number == "INV-ACME-007"


@pytest.mark.asyncio
async def test_quote_to_invoice_regenerates_number(db_session, test_client):
    quote = await InvoiceService.create_invoice(
        db_session,
        client_id=test_client.id,
        issue_date=date(2026, 3, 3),
        document_type="quote",
        items=_items(),
    )
    assert quote.invoice_number == "Q-20260303-1"

    updated = await InvoiceService.update_invoice(db_session, quote.id, document_type="invoice")
    assert updated.document_type == "invoice"
    assert updated.invoice_number == "20260303-1"


@pytest.mark.asyncio
async def test_duplicate_override_number_raises(db_session, test_client):
    await InvoiceService.create_invoice(
        db_session, client_id=test_client.id, invoice_number_override="DUP-1", items=_items()
    )
    with pytest.raises(ValueError, match="already exists"):
        await InvoiceService.create_invoice(
            db_session, client_id=test_client.id, invoice_number_override="DUP-1", items=_items()
        )


@pytest.mark.asyncio
async def test_update_kwargs_cannot_set_computed_totals(db_session, test_client):
    """The kwargs allow-list must not let callers overwrite computed money fields."""
    from decimal import Decimal

    inv = await InvoiceService.create_invoice(
        db_session, client_id=test_client.id, items=_items()
    )
    assert inv.total == Decimal("100.00")

    # Attempt to inject a bogus total via kwargs — must be ignored.
    updated = await InvoiceService.update_invoice(db_session, inv.id, total=Decimal("99999.00"))
    assert updated.total == Decimal("100.00")


@pytest.mark.asyncio
async def test_recurring_catches_up_missed_periods(db_session, test_client, monkeypatch):
    """A monthly schedule months overdue generates one invoice per missed period."""
    monkeypatch.setattr("invoice_machine.service.recurring.utc_now", _fixed_now(2026, 4, 15))

    schedule = await RecurringService.create_schedule(
        db_session,
        client_id=test_client.id,
        name="Monthly Retainer",
        frequency="monthly",
        schedule_day=1,
        next_invoice_date=date(2026, 1, 1),
        line_items=[{"description": "Retainer", "quantity": 1, "unit_price": "100"}],
    )

    results = await RecurringService.process_due_schedules(db_session)
    successes = [r for r in results if r.get("success")]

    # Periods 2026-01-01, 02-01, 03-01, 04-01 are due (<= 2026-04-15); 05-01 is not.
    assert len(successes) == 4
    assert sorted(r["issue_date"] for r in successes) == [
        "2026-01-01",
        "2026-02-01",
        "2026-03-01",
        "2026-04-01",
    ]

    await db_session.refresh(schedule)
    assert schedule.next_invoice_date == date(2026, 5, 1)

    # Running again generates nothing new (idempotent once caught up).
    again = await RecurringService.process_due_schedules(db_session)
    assert [r for r in again if r.get("success")] == []
