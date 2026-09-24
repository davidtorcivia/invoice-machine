"""Invoice status, terms and validation rules shared by REST and MCP."""

from datetime import timedelta
from decimal import Decimal

import pytest

from invoice_machine.service.clients import ClientService
from invoice_machine.service.email import send_invoice_email
from invoice_machine.service.invoices import InvoiceService
from invoice_machine.service.payments import PaymentService
from invoice_machine.utils import utc_now


async def _draft(db_session, test_client, total="100.00", **kwargs):
    return await InvoiceService.create_invoice(
        db_session,
        client_id=test_client.id,
        items=[{"description": "Service", "quantity": 1, "unit_price": total}],
        **kwargs,
    )


class TestDueOnReceipt:
    """payment_terms_days=0 means due on receipt, not "unset"."""

    @pytest.mark.asyncio
    async def test_zero_terms_make_the_invoice_due_on_issue(
        self, db_session, business_profile, test_client
    ):
        invoice = await _draft(db_session, test_client, payment_terms_days=0)

        assert invoice.payment_terms_days == 0
        assert invoice.due_date == invoice.issue_date

    @pytest.mark.asyncio
    async def test_zero_terms_on_the_client_are_inherited(
        self, db_session, business_profile, test_client
    ):
        test_client.payment_terms_days = 0
        await db_session.commit()

        invoice = await _draft(db_session, test_client)

        assert invoice.payment_terms_days == 0
        assert invoice.due_date == invoice.issue_date

    @pytest.mark.asyncio
    async def test_quote_conversion_keeps_zero_terms(
        self, db_session, business_profile, test_client
    ):
        quote = await _draft(db_session, test_client, document_type="quote", payment_terms_days=0)

        invoice = await InvoiceService.convert_quote_to_invoice(db_session, quote.id)

        assert invoice is not None
        assert invoice.payment_terms_days == 0
        assert invoice.due_date == invoice.issue_date


class TestPaidDraftLeavesDraft:
    """A draft paid in full settles to paid once it is issued."""

    async def _paid_draft(self, db_session, test_client):
        invoice = await _draft(db_session, test_client)
        await PaymentService.record_payment(db_session, invoice.id, amount="100.00")
        await db_session.refresh(invoice)
        assert invoice.status == "draft"
        return invoice

    @pytest.mark.asyncio
    async def test_status_update_to_sent(self, db_session, business_profile, test_client):
        invoice = await self._paid_draft(db_session, test_client)

        updated = await InvoiceService.update_invoice(db_session, invoice.id, status="sent")

        assert updated.status == "paid"
        assert updated.paid_at is not None

    @pytest.mark.asyncio
    async def test_bulk_mark_sent(self, db_session, business_profile, test_client):
        invoice = await self._paid_draft(db_session, test_client)

        result = await InvoiceService.bulk_action(db_session, "mark_sent", [invoice.id])
        await db_session.refresh(invoice)

        assert result["successful"] == 1
        assert invoice.status == "paid"
        assert invoice.paid_at is not None

    @pytest.mark.asyncio
    async def test_email_send(self, db_session, business_profile, test_client, monkeypatch):
        from unittest.mock import AsyncMock

        invoice = await self._paid_draft(db_session, test_client)
        business_profile.smtp_enabled = 1
        await db_session.commit()
        monkeypatch.setattr(
            "invoice_machine.pdf.generator.store_invoice_pdf", AsyncMock(return_value="pdfs/x.pdf")
        )
        monkeypatch.setattr(
            "invoice_machine.email.EmailService.send_invoice",
            AsyncMock(return_value={"success": True}),
        )

        await send_invoice_email(db_session, invoice.id)
        await db_session.refresh(invoice)

        assert invoice.status == "paid"
        assert invoice.paid_at is not None


class TestServiceLayerBounds:
    """MCP skips the REST schemas, so the service enforces the ranges."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"tax_rate": Decimal("150")},
            {"tax_rate": Decimal("-1")},
            {"payment_terms_days": -1},
            {"payment_terms_days": 366},
            {"document_type": "memo"},
        ],
    )
    async def test_update_invoice_rejects_out_of_range(
        self, db_session, business_profile, test_client, kwargs
    ):
        invoice = await _draft(db_session, test_client)

        with pytest.raises(ValueError):
            await InvoiceService.update_invoice(db_session, invoice.id, **kwargs)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kwargs",
        [{"payment_terms_days": -5}, {"document_type": "memo"}, {"tax_rate": Decimal("101")}],
    )
    async def test_create_invoice_rejects_out_of_range(
        self, db_session, business_profile, test_client, kwargs
    ):
        with pytest.raises(ValueError):
            await _draft(db_session, test_client, **kwargs)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kwargs", [{"tax_rate": Decimal("101")}, {"payment_terms_days": -1}])
    async def test_client_create_and_update_reject_out_of_range(
        self, db_session, test_client, kwargs
    ):
        with pytest.raises(ValueError):
            await ClientService.create_client(db_session, name="Bad", **kwargs)
        with pytest.raises(ValueError):
            await ClientService.update_client(db_session, test_client.id, **kwargs)


class TestUpdateOrdering:
    @pytest.mark.asyncio
    async def test_paid_with_a_tax_change_settles_the_new_total(
        self, db_session, business_profile, test_client
    ):
        invoice = await _draft(db_session, test_client, tax_enabled=False)
        await InvoiceService.update_invoice(db_session, invoice.id, status="sent")

        updated = await InvoiceService.update_invoice(
            db_session,
            invoice.id,
            status="paid",
            tax_enabled=True,
            tax_rate=Decimal("10"),
        )

        assert updated.total == Decimal("110.00")
        assert updated.status == "paid"
        assert updated.amount_due == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_unpaying_with_a_tax_change_drops_the_marked_paid_row(
        self, db_session, business_profile, test_client
    ):
        invoice = await _draft(db_session, test_client, tax_enabled=False)
        await InvoiceService.update_invoice(db_session, invoice.id, status="paid")

        updated = await InvoiceService.update_invoice(
            db_session,
            invoice.id,
            status="sent",
            tax_enabled=True,
            tax_rate=Decimal("10"),
        )

        assert updated.status == "sent"
        assert updated.amount_paid == Decimal("0.00")
        assert updated.amount_due == Decimal("110.00")

    @pytest.mark.asyncio
    async def test_overdue_moved_to_a_future_due_date_is_sent_again(
        self, db_session, business_profile, test_client
    ):
        today = utc_now().date()
        invoice = await _draft(
            db_session,
            test_client,
            issue_date=today - timedelta(days=40),
            due_date=today - timedelta(days=10),
        )
        await InvoiceService.update_invoice(db_session, invoice.id, status="sent")
        await InvoiceService.update_overdue_invoices(db_session)
        await db_session.refresh(invoice)
        assert invoice.status == "overdue"

        updated = await InvoiceService.update_invoice(
            db_session, invoice.id, due_date=today + timedelta(days=5)
        )

        assert updated.status == "sent"

        # Overdue set by hand on a future due date survives an unrelated edit.
        await InvoiceService.update_invoice(db_session, invoice.id, status="overdue")
        kept = await InvoiceService.update_invoice(db_session, invoice.id, notes="n")
        assert kept.status == "overdue"
