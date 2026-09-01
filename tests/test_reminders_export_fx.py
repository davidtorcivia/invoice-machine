"""Tests for payment reminders, CSV export, and multi-currency consolidation."""

import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from invoice_machine.service import analytics as analytics_service
from invoice_machine.service.export import export_csv_text
from invoice_machine.service.reminders import (
    build_reminder_content,
    due_offsets_for,
    send_due_reminders,
    validate_reminder_offsets,
)
from invoice_machine.services import InvoiceService, PaymentService
from invoice_machine.utils import utc_now


class TestReminderSchedule:
    """Offset validation and which reminders come due."""

    def test_offsets_are_sorted_and_deduplicated(self):
        assert validate_reminder_offsets([7, -3, 7, 1]) == [-3, 1, 7]

    def test_out_of_range_offsets_are_rejected(self):
        for bad in ([400], [-400]):
            with pytest.raises(ValueError, match="between"):
                validate_reminder_offsets(bad)

    def test_too_many_offsets_are_rejected(self):
        with pytest.raises(ValueError, match="At most 10"):
            validate_reminder_offsets(list(range(11)))

    def test_non_numeric_offsets_are_rejected(self):
        with pytest.raises(ValueError, match="whole numbers"):
            validate_reminder_offsets(["soon"])

    @pytest.mark.asyncio
    async def test_offset_fires_on_its_day(self, db_session, business_profile, test_client):
        invoice = await InvoiceService.create_invoice(db_session, client_id=test_client.id)
        today = utc_now().date()
        invoice.due_date = today - timedelta(days=7)

        # -3 and 1 have also passed but are superseded by 7.
        assert due_offsets_for(invoice, [-3, 1, 7, 14], today) == [-3, 1, 7]

    @pytest.mark.asyncio
    async def test_already_sent_offsets_do_not_refire(
        self, db_session, business_profile, test_client
    ):
        invoice = await InvoiceService.create_invoice(db_session, client_id=test_client.id)
        today = utc_now().date()
        invoice.due_date = today - timedelta(days=7)
        invoice.reminders_sent = json.dumps([-3, 1, 7])

        assert due_offsets_for(invoice, [-3, 1, 7, 14], today) == []

    @pytest.mark.asyncio
    async def test_enabling_reminders_late_sends_only_the_latest(
        self, db_session, business_profile, test_client
    ):
        """Turning reminders on for an old invoice must not send a burst of four."""
        invoice = await InvoiceService.create_invoice(db_session, client_id=test_client.id)
        today = utc_now().date()
        invoice.due_date = today - timedelta(days=90)

        assert due_offsets_for(invoice, [-3, 1, 7, 14], today) == [-3, 1, 7, 14]

    @pytest.mark.asyncio
    async def test_invoice_without_due_date_is_skipped(
        self, db_session, business_profile, test_client
    ):
        invoice = await InvoiceService.create_invoice(db_session, client_id=test_client.id)
        invoice.due_date = None
        assert due_offsets_for(invoice, [1, 7], utc_now().date()) == []


class TestReminderSending:
    """The daily sweep."""

    async def _reminder_setup(self, db_session, business_profile, test_client, days_overdue=7):
        business_profile.reminders_enabled = 1
        business_profile.smtp_enabled = 1
        business_profile.reminder_offsets = json.dumps([-3, 1, 7, 14])
        await db_session.commit()

        invoice = await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            items=[{"description": "Service", "quantity": 1, "unit_price": 500}],
        )
        await InvoiceService.update_invoice(db_session, invoice.id, status="sent")
        await db_session.refresh(invoice)
        invoice.due_date = utc_now().date() - timedelta(days=days_overdue)
        invoice.client_email = "client@example.com"
        await db_session.commit()
        return invoice

    @pytest.mark.asyncio
    async def test_reminder_is_sent_and_recorded(self, db_session, business_profile, test_client):
        invoice = await self._reminder_setup(db_session, business_profile, test_client)

        with patch(
            "invoice_machine.service.email.send_invoice_email",
            new=AsyncMock(return_value={"success": True, "recipient": "client@example.com"}),
        ):
            results = await send_due_reminders(db_session)

        assert len(results) == 1
        assert results[0]["success"] is True
        await db_session.refresh(invoice)
        assert 7 in invoice.reminders_sent_list
        assert invoice.last_reminder_sent_at is not None

    @pytest.mark.asyncio
    async def test_running_twice_sends_once(self, db_session, business_profile, test_client):
        await self._reminder_setup(db_session, business_profile, test_client)

        sender = AsyncMock(return_value={"success": True, "recipient": "client@example.com"})
        with patch("invoice_machine.service.email.send_invoice_email", new=sender):
            await send_due_reminders(db_session)
            await send_due_reminders(db_session)

        assert sender.await_count == 1

    @pytest.mark.asyncio
    async def test_failed_send_is_not_recorded_so_it_retries(
        self, db_session, business_profile, test_client
    ):
        invoice = await self._reminder_setup(db_session, business_profile, test_client)

        with patch(
            "invoice_machine.service.email.send_invoice_email",
            new=AsyncMock(return_value={"success": False, "error": "SMTP down"}),
        ):
            results = await send_due_reminders(db_session)

        assert results[0]["success"] is False
        await db_session.refresh(invoice)
        assert invoice.reminders_sent_list == []

    @pytest.mark.asyncio
    async def test_one_failing_reminder_does_not_abort_the_sweep(
        self, db_session, business_profile, test_client
    ):
        first = await self._reminder_setup(db_session, business_profile, test_client)
        second = await self._reminder_setup(db_session, business_profile, test_client)
        first_id = first.id
        updated_before = second.updated_at

        async def fail_first(session, invoice_id, **kwargs):
            if invoice_id == first_id:
                raise RuntimeError("renderer exploded")
            return {"success": True, "recipient": "client@example.com"}

        with patch("invoice_machine.service.email.send_invoice_email", new=fail_first):
            results = await send_due_reminders(db_session)

        assert [r["success"] for r in results] == [False, True]
        await db_session.refresh(second)
        assert second.reminders_sent_list == [-3, 1, 7]
        # The reminder bookkeeping must not mark the invoice stale for PDF purposes.
        assert second.updated_at.replace(tzinfo=None) == updated_before.replace(tzinfo=None)

    @pytest.mark.asyncio
    async def test_fully_paid_invoice_is_not_chased(
        self, db_session, business_profile, test_client
    ):
        invoice = await self._reminder_setup(db_session, business_profile, test_client)
        await PaymentService.record_payment(db_session, invoice.id, amount="500.00")

        sender = AsyncMock(return_value={"success": True})
        with patch("invoice_machine.service.email.send_invoice_email", new=sender):
            results = await send_due_reminders(db_session)

        assert results == []
        assert sender.await_count == 0

    @pytest.mark.asyncio
    async def test_partially_paid_invoice_is_still_chased(
        self, db_session, business_profile, test_client
    ):
        invoice = await self._reminder_setup(db_session, business_profile, test_client)
        await PaymentService.record_payment(db_session, invoice.id, amount="100.00")

        with patch(
            "invoice_machine.service.email.send_invoice_email",
            new=AsyncMock(return_value={"success": True, "recipient": "client@example.com"}),
        ):
            results = await send_due_reminders(db_session)

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_disabled_reminders_do_nothing(self, db_session, business_profile, test_client):
        await self._reminder_setup(db_session, business_profile, test_client)
        business_profile.reminders_enabled = 0
        await db_session.commit()

        assert await send_due_reminders(db_session) == []

    @pytest.mark.asyncio
    async def test_reminder_body_reports_the_outstanding_balance(
        self, db_session, business_profile, test_client
    ):
        invoice = await self._reminder_setup(db_session, business_profile, test_client)
        await PaymentService.record_payment(db_session, invoice.id, amount="200.00")
        await db_session.refresh(invoice)

        subject, body = build_reminder_content(invoice, business_profile, 7)
        assert "7 days overdue" in subject or "7 days overdue" in body
        assert "$300.00" in body


class TestCsvExport:
    """CSV shape and content."""

    @pytest.mark.asyncio
    async def test_invoice_export_has_header_and_rows(
        self, db_session, business_profile, test_client
    ):
        invoice = await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            items=[{"description": "Consulting", "quantity": 2, "unit_price": 250}],
        )
        await PaymentService.record_payment(db_session, invoice.id, amount="100.00")

        csv_text = await export_csv_text(db_session, "invoices")
        lines = csv_text.strip().splitlines()

        assert "invoice_number" in lines[0]
        assert "amount_due" in lines[0]
        assert invoice.invoice_number in csv_text
        # Money is plain decimals with a separate currency column.
        assert "500.00" in csv_text
        assert "400.00" in csv_text
        assert "$" not in csv_text

    @pytest.mark.asyncio
    async def test_line_item_export_is_one_row_per_item(
        self, db_session, business_profile, test_client
    ):
        await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            items=[
                {"description": "Design", "quantity": 1, "unit_price": 100},
                {"description": "Build", "quantity": 3, "unit_price": 200},
            ],
        )
        csv_text = await export_csv_text(db_session, "line_items")
        assert len(csv_text.strip().splitlines()) == 3  # header + 2 items
        assert "Design" in csv_text and "Build" in csv_text

    @pytest.mark.asyncio
    async def test_payment_export(self, db_session, business_profile, test_client):
        invoice = await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            items=[{"description": "Service", "quantity": 1, "unit_price": 400}],
        )
        await PaymentService.record_payment(
            db_session, invoice.id, amount="150.00", method="bank_transfer", reference="REF-9"
        )

        csv_text = await export_csv_text(db_session, "payments")
        assert "bank_transfer" in csv_text
        assert "REF-9" in csv_text
        assert "150.00" in csv_text

    @pytest.mark.asyncio
    async def test_fields_with_commas_are_quoted(self, db_session, business_profile, test_client):
        await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            items=[{"description": 'Design, build, and "launch"', "quantity": 1, "unit_price": 1}],
        )
        csv_text = await export_csv_text(db_session, "line_items")
        # csv module escapes embedded quotes by doubling them.
        assert '"Design, build, and ""launch"""' in csv_text

    @pytest.mark.asyncio
    async def test_unknown_kind_is_rejected(self, db_session):
        with pytest.raises(ValueError, match="Unknown export kind"):
            await export_csv_text(db_session, "nonsense")

    @pytest.mark.asyncio
    async def test_max_rows_truncates_and_says_so(self, db_session, business_profile, test_client):
        for _ in range(5):
            await InvoiceService.create_invoice(db_session, client_id=test_client.id)

        csv_text = await export_csv_text(db_session, "invoices", max_rows=2)
        assert "# truncated at 2 rows" in csv_text


class TestConsolidatedReporting:
    """Opt-in multi-currency roll-up, with explicit coverage reporting."""

    async def _invoice(self, db_session, test_client, currency, amount, rate=None):
        invoice = await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            currency_code=currency,
            exchange_rate=rate,
            items=[{"description": "Service", "quantity": 1, "unit_price": amount}],
        )
        await InvoiceService.update_invoice(db_session, invoice.id, status="sent")
        return invoice

    @pytest.mark.asyncio
    async def test_base_currency_invoice_gets_rate_one(
        self, db_session, business_profile, test_client
    ):
        invoice = await self._invoice(db_session, test_client, "USD", 100)
        assert invoice.exchange_rate == Decimal("1")
        assert invoice.base_currency_code == "USD"

    @pytest.mark.asyncio
    async def test_profile_rate_table_is_applied_at_issue(
        self, db_session, business_profile, test_client
    ):
        business_profile.fx_rates = json.dumps({"EUR": "1.10"})
        await db_session.commit()

        invoice = await self._invoice(db_session, test_client, "EUR", 100)
        assert invoice.exchange_rate == Decimal("1.10")

    @pytest.mark.asyncio
    async def test_explicit_rate_wins_over_the_table(
        self, db_session, business_profile, test_client
    ):
        business_profile.fx_rates = json.dumps({"EUR": "1.10"})
        await db_session.commit()

        invoice = await self._invoice(db_session, test_client, "EUR", 100, rate=Decimal("1.25"))
        assert invoice.exchange_rate == Decimal("1.25")

    @pytest.mark.asyncio
    async def test_consolidation_converts_and_reports_full_coverage(
        self, db_session, business_profile, test_client
    ):
        business_profile.fx_rates = json.dumps({"EUR": "1.10"})
        await db_session.commit()

        await self._invoice(db_session, test_client, "USD", 100)
        await self._invoice(db_session, test_client, "EUR", 100)

        summary = await analytics_service.consolidated_summary(db_session)
        assert summary["currency"] == "USD"
        assert summary["invoiced"] == "210.00"  # 100 + (100 * 1.10)
        assert summary["coverage"]["complete"] is True
        assert summary["coverage"]["uncovered_invoices"] == 0

    @pytest.mark.asyncio
    async def test_unconvertible_invoices_are_excluded_and_reported(
        self, db_session, business_profile, test_client
    ):
        """A missing rate must never be silently treated as 1:1."""
        await self._invoice(db_session, test_client, "USD", 100)
        # No rate configured for GBP, and none supplied.
        await self._invoice(db_session, test_client, "GBP", 500)

        summary = await analytics_service.consolidated_summary(db_session)
        assert summary["invoiced"] == "100.00"
        assert summary["coverage"]["complete"] is False
        assert summary["coverage"]["uncovered_invoices"] == 1
        assert summary["coverage"]["uncovered_by_currency"] == {"GBP": 1}

    @pytest.mark.asyncio
    async def test_consolidation_includes_payments_and_outstanding(
        self, db_session, business_profile, test_client
    ):
        business_profile.fx_rates = json.dumps({"EUR": "2"})
        await db_session.commit()

        invoice = await self._invoice(db_session, test_client, "EUR", 100)
        await PaymentService.record_payment(db_session, invoice.id, amount="40.00")

        summary = await analytics_service.consolidated_summary(db_session)
        assert summary["invoiced"] == "200.00"
        assert summary["paid"] == "80.00"
        assert summary["outstanding"] == "120.00"


class TestSupersededReminders:
    """Passed-but-unsent offsets must not drip out over following days."""

    @pytest.mark.asyncio
    async def test_older_offsets_are_marked_sent_not_queued(
        self, db_session, business_profile, test_client
    ):
        """Enabling reminders on a long-overdue invoice sends exactly one email.

        The earlier offsets are recorded as sent without being delivered — left
        pending they would have fired on subsequent days, chasing the client with
        progressively *staler* reminders in reverse order.
        """
        business_profile.reminders_enabled = 1
        business_profile.smtp_enabled = 1
        business_profile.reminder_offsets = json.dumps([-3, 1, 7, 14])
        await db_session.commit()

        invoice = await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            items=[{"description": "Service", "quantity": 1, "unit_price": 500}],
        )
        await InvoiceService.update_invoice(db_session, invoice.id, status="sent")
        await db_session.refresh(invoice)
        invoice.due_date = utc_now().date() - timedelta(days=90)
        invoice.client_email = "client@example.com"
        await db_session.commit()

        sender = AsyncMock(return_value={"success": True, "recipient": "client@example.com"})
        with patch("invoice_machine.service.email.send_invoice_email", new=sender):
            first = await send_due_reminders(db_session)
            second = await send_due_reminders(db_session)
            third = await send_due_reminders(db_session)

        assert sender.await_count == 1
        assert first[0]["offset"] == 14
        assert first[0]["superseded_offsets"] == [-3, 1, 7]
        assert second == [] and third == []

        await db_session.refresh(invoice)
        assert invoice.reminders_sent_list == [-3, 1, 7, 14]


class TestReminderTimezone:
    """Reminder timing follows the business's local clock, not UTC."""

    def test_valid_timezone_accepted(self):
        from invoice_machine.service.reminders import validate_timezone

        assert validate_timezone("America/New_York") == "America/New_York"
        assert validate_timezone("") == "UTC"

    def test_unknown_timezone_rejected(self):
        from invoice_machine.service.reminders import validate_timezone

        with pytest.raises(ValueError, match="Unknown timezone"):
            validate_timezone("Mars/Olympus_Mons")

    @pytest.mark.asyncio
    async def test_business_now_follows_configured_zone(self, db_session, business_profile):
        from invoice_machine.service.reminders import business_now

        business_profile.business_timezone = "Pacific/Auckland"
        await db_session.commit()

        local = business_now(business_profile)
        assert str(local.tzinfo) == "Pacific/Auckland"
        assert local.utcoffset() != timedelta(0)

    @pytest.mark.asyncio
    async def test_corrupt_timezone_falls_back_to_utc(self, db_session, business_profile):
        """A bad stored value must not stop reminders going out entirely."""
        from invoice_machine.service.reminders import business_now

        business_profile.business_timezone = "Not/AZone"
        await db_session.commit()

        assert business_now(business_profile).utcoffset() == timedelta(0)

    @pytest.mark.asyncio
    async def test_days_overdue_counted_in_local_time(
        self, db_session, business_profile, test_client
    ):
        """An invoice due locally today is not yet overdue, whatever UTC says."""
        from invoice_machine.service.reminders import business_now, due_offsets_for

        business_profile.business_timezone = "Pacific/Auckland"
        await db_session.commit()

        invoice = await InvoiceService.create_invoice(db_session, client_id=test_client.id)
        local_today = business_now(business_profile).date()
        invoice.due_date = local_today

        # Offset 0 is "on the due date"; offset 1 has not arrived yet.
        assert due_offsets_for(invoice, [0, 1], local_today) == [0]
        assert due_offsets_for(invoice, [1], local_today) == []
