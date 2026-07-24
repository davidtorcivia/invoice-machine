"""Tests for payment tracking, partial payments and A/R aging."""

from datetime import timedelta
from decimal import Decimal

import pytest

from invoice_machine.services import InvoiceService, PaymentService
from invoice_machine.utils import utc_now


async def _invoice(db_session, test_client, total=Decimal("1000.00"), status="sent", due_days=30):
    invoice = await InvoiceService.create_invoice(
        db_session,
        client_id=test_client.id,
        items=[{"description": "Service", "quantity": 1, "unit_price": total}],
        payment_terms_days=due_days,
    )
    if status != "draft":
        await InvoiceService.update_invoice(db_session, invoice.id, status=status)
        await db_session.refresh(invoice)
    return invoice


class TestPartialPayments:
    """Recording payments and the resulting balance/status."""

    @pytest.mark.asyncio
    async def test_partial_payment_leaves_balance_and_status(
        self, db_session, business_profile, test_client
    ):
        invoice = await _invoice(db_session, test_client)

        await PaymentService.record_payment(db_session, invoice.id, amount="400.00")
        await db_session.refresh(invoice)

        assert invoice.amount_paid == Decimal("400.00")
        assert invoice.amount_due == Decimal("600.00")
        assert invoice.is_partially_paid is True
        # Still owed, so it must not read as paid.
        assert invoice.status == "sent"

    @pytest.mark.asyncio
    async def test_payments_totalling_the_invoice_mark_it_paid(
        self, db_session, business_profile, test_client
    ):
        invoice = await _invoice(db_session, test_client)

        await PaymentService.record_payment(db_session, invoice.id, amount="400.00")
        await PaymentService.record_payment(db_session, invoice.id, amount="600.00")
        await db_session.refresh(invoice)

        assert invoice.amount_due == Decimal("0.00")
        assert invoice.is_partially_paid is False
        assert invoice.status == "paid"
        assert invoice.paid_at is not None

    @pytest.mark.asyncio
    async def test_deleting_a_payment_reverts_a_paid_invoice(
        self, db_session, business_profile, test_client
    ):
        invoice = await _invoice(db_session, test_client)
        payment = await PaymentService.record_payment(db_session, invoice.id, amount="1000.00")
        await db_session.refresh(invoice)
        assert invoice.status == "paid"

        await PaymentService.delete_payment(db_session, payment.id)
        await db_session.refresh(invoice)

        assert invoice.amount_paid == Decimal("0.00")
        assert invoice.status == "sent"
        assert invoice.paid_at is None

    @pytest.mark.asyncio
    async def test_reverted_payment_returns_to_overdue_when_past_due(
        self, db_session, business_profile, test_client
    ):
        invoice = await _invoice(db_session, test_client)
        invoice.due_date = utc_now().date() - timedelta(days=5)
        await db_session.commit()

        payment = await PaymentService.record_payment(db_session, invoice.id, amount="1000.00")
        await PaymentService.delete_payment(db_session, payment.id)
        await db_session.refresh(invoice)

        assert invoice.status == "overdue"

    @pytest.mark.asyncio
    async def test_overpayment_is_refused_without_opt_in(
        self, db_session, business_profile, test_client
    ):
        invoice = await _invoice(db_session, test_client)

        with pytest.raises(ValueError, match="exceeds the outstanding balance"):
            await PaymentService.record_payment(db_session, invoice.id, amount="1500.00")

        payment = await PaymentService.record_payment(
            db_session, invoice.id, amount="1500.00", allow_overpayment=True
        )
        assert payment is not None
        await db_session.refresh(invoice)
        # Overpaid, but the balance never goes negative.
        assert invoice.amount_paid == Decimal("1500.00")
        assert invoice.amount_due == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_non_positive_amounts_are_rejected(
        self, db_session, business_profile, test_client
    ):
        invoice = await _invoice(db_session, test_client)
        for bad in ("0", "-10", "abc"):
            with pytest.raises(ValueError):
                await PaymentService.record_payment(db_session, invoice.id, amount=bad)

    @pytest.mark.asyncio
    async def test_payment_against_missing_invoice_returns_none(self, db_session):
        assert await PaymentService.record_payment(db_session, 999999, amount="10") is None

    @pytest.mark.asyncio
    async def test_cancelled_invoice_rejects_payments(
        self, db_session, business_profile, test_client
    ):
        invoice = await _invoice(db_session, test_client, status="cancelled")

        with pytest.raises(ValueError, match="cancelled"):
            await PaymentService.record_payment(db_session, invoice.id, amount="10")

    @pytest.mark.asyncio
    async def test_payment_snapshots_the_invoice_currency(
        self, db_session, business_profile, test_client
    ):
        invoice = await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            currency_code="EUR",
            items=[{"description": "Service", "quantity": 1, "unit_price": 100}],
        )
        payment = await PaymentService.record_payment(db_session, invoice.id, amount="50")
        assert payment.currency_code == "EUR"

    @pytest.mark.asyncio
    async def test_duplicate_external_id_records_once(
        self, db_session, business_profile, test_client
    ):
        """Webhook idempotency: the same provider event must land only once."""
        invoice = await _invoice(db_session, test_client)

        first = await PaymentService.record_payment(
            db_session, invoice.id, amount="100", provider="stripe", external_id="evt_1"
        )
        second = await PaymentService.record_payment(
            db_session, invoice.id, amount="100", provider="stripe", external_id="evt_1"
        )

        assert first.id == second.id
        await db_session.refresh(invoice)
        assert invoice.amount_paid == Decimal("100.00")


class TestAgingReport:
    """A/R aging buckets."""

    @pytest.mark.asyncio
    async def test_buckets_by_days_overdue(self, db_session, business_profile, test_client):
        today = utc_now().date()
        expectations = {0: "current", 10: "1_30", 45: "31_60", 75: "61_90", 200: "over_90"}

        created = {}
        for days, bucket in expectations.items():
            invoice = await _invoice(db_session, test_client, total=Decimal("100.00"))
            invoice.due_date = today - timedelta(days=days)
            await db_session.commit()
            created[invoice.id] = bucket

        report = await PaymentService.aging_report(db_session)
        actual = {item["invoice_id"]: item["bucket"] for item in report["invoices"]}

        for invoice_id, expected_bucket in created.items():
            assert actual[invoice_id] == expected_bucket

    @pytest.mark.asyncio
    async def test_aging_uses_outstanding_not_total(
        self, db_session, business_profile, test_client
    ):
        invoice = await _invoice(db_session, test_client, total=Decimal("1000.00"))
        invoice.due_date = utc_now().date() - timedelta(days=10)
        await db_session.commit()
        await PaymentService.record_payment(db_session, invoice.id, amount="250.00")

        report = await PaymentService.aging_report(db_session)
        entry = next(i for i in report["invoices"] if i["invoice_id"] == invoice.id)
        assert entry["amount_due"] == "750.00"
        assert report["by_currency"]["USD"]["buckets"]["1_30"] == "750.00"

    @pytest.mark.asyncio
    async def test_aging_never_mixes_currencies(self, db_session, business_profile, test_client):
        for currency in ("USD", "EUR"):
            invoice = await InvoiceService.create_invoice(
                db_session,
                client_id=test_client.id,
                currency_code=currency,
                items=[{"description": "Service", "quantity": 1, "unit_price": 100}],
            )
            await InvoiceService.update_invoice(db_session, invoice.id, status="sent")

        report = await PaymentService.aging_report(db_session)
        assert set(report["by_currency"]) == {"USD", "EUR"}
        assert report["by_currency"]["USD"]["total_outstanding"] == "100.00"
        assert report["by_currency"]["EUR"]["total_outstanding"] == "100.00"

    @pytest.mark.asyncio
    async def test_paid_draft_and_quote_are_excluded(
        self, db_session, business_profile, test_client
    ):
        paid = await _invoice(db_session, test_client)
        await PaymentService.record_payment(db_session, paid.id, amount="1000.00")
        await _invoice(db_session, test_client, status="draft")
        quote = await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            document_type="quote",
            items=[{"description": "Service", "quantity": 1, "unit_price": 500}],
        )
        await InvoiceService.update_invoice(db_session, quote.id, status="sent")

        report = await PaymentService.aging_report(db_session)
        assert report["invoices"] == []


class TestQuoteConversion:
    """Quote -> invoice conversion keeps both documents and links them."""

    @pytest.mark.asyncio
    async def test_conversion_creates_a_linked_invoice(
        self, db_session, business_profile, test_client
    ):
        quote = await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            document_type="quote",
            notes="As discussed",
            items=[
                {"description": "Design", "quantity": 2, "unit_price": 500},
                {"description": "Hosting", "quantity": 1, "unit_price": 100},
            ],
        )
        quote_number = quote.invoice_number

        invoice = await InvoiceService.convert_quote_to_invoice(db_session, quote.id)
        await db_session.refresh(quote)

        # The quote survives intact — it is the document the client accepted.
        assert quote.document_type == "quote"
        assert quote.invoice_number == quote_number
        assert quote.converted_to_invoice_id == invoice.id

        assert invoice.document_type == "invoice"
        assert invoice.converted_from_invoice_id == quote.id
        assert invoice.total == quote.total
        assert len(invoice.items) == 2
        assert invoice.notes == "As discussed"

    @pytest.mark.asyncio
    async def test_conversion_carries_the_accepted_tax_snapshot(
        self, db_session, business_profile, test_client
    ):
        quote = await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            document_type="quote",
            tax_enabled=True,
            tax_rate=Decimal("10.00"),
            tax_name="VAT",
            items=[{"description": "Service", "quantity": 1, "unit_price": 1000}],
        )
        assert quote.total == Decimal("1100.00")

        # Changing the global default afterwards must not change what is billed.
        business_profile.default_tax_rate = Decimal("25.00")
        await db_session.commit()

        invoice = await InvoiceService.convert_quote_to_invoice(db_session, quote.id)
        assert invoice.tax_rate == Decimal("10.00")
        assert invoice.tax_name == "VAT"
        assert invoice.total == Decimal("1100.00")

    @pytest.mark.asyncio
    async def test_double_conversion_is_refused(self, db_session, business_profile, test_client):
        quote = await InvoiceService.create_invoice(
            db_session, client_id=test_client.id, document_type="quote"
        )
        await InvoiceService.convert_quote_to_invoice(db_session, quote.id)

        with pytest.raises(ValueError, match="already converted"):
            await InvoiceService.convert_quote_to_invoice(db_session, quote.id)

    @pytest.mark.asyncio
    async def test_converting_an_invoice_is_refused(
        self, db_session, business_profile, test_client
    ):
        invoice = await InvoiceService.create_invoice(db_session, client_id=test_client.id)

        with pytest.raises(ValueError, match="Only quotes"):
            await InvoiceService.convert_quote_to_invoice(db_session, invoice.id)

    @pytest.mark.asyncio
    async def test_converting_a_missing_quote_returns_none(self, db_session):
        assert await InvoiceService.convert_quote_to_invoice(db_session, 999999) is None
