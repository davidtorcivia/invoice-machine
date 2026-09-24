"""Tests for business logic services."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from invoice_machine.config import get_settings
from invoice_machine.database import Client, Invoice, InvoiceItem
from invoice_machine.service.clients import ClientService
from invoice_machine.service.common import (
    calculate_due_date,
    format_currency,
    generate_invoice_number,
    purge_trashed_records,
    recalculate_invoice_totals,
    snapshot_client_info,
)
from invoice_machine.service.invoices import InvoiceService
from invoice_machine.utils import utc_now


class TestInvoiceNumberGeneration:
    """Tests for invoice number generation."""

    @pytest.mark.asyncio
    async def test_first_invoice_of_day(self, db_session):
        num = await generate_invoice_number(db_session, date(2025, 1, 15))
        assert num == "20250115-1"

    @pytest.mark.asyncio
    async def test_second_invoice_of_day(self, db_session):
        invoice = Invoice(
            invoice_number="20250115-1",
            client_id=None,
            issue_date=date(2025, 1, 15),
            status="draft",
        )
        db_session.add(invoice)
        await db_session.commit()

        num = await generate_invoice_number(db_session, date(2025, 1, 15))
        assert num == "20250115-2"

    @pytest.mark.asyncio
    async def test_different_day_resets_sequence(self, db_session):
        invoice = Invoice(
            invoice_number="20250114-5",
            client_id=None,
            issue_date=date(2025, 1, 14),
            status="draft",
        )
        db_session.add(invoice)
        await db_session.commit()

        num = await generate_invoice_number(db_session, date(2025, 1, 15))
        assert num == "20250115-1"

    @pytest.mark.asyncio
    async def test_ignores_malformed_numbers(self, db_session):
        for num in ["20250115-bad", "not-a-number", "20250115-"]:
            invoice = Invoice(
                invoice_number=num,
                client_id=None,
                issue_date=date(2025, 1, 15),
                status="draft",
            )
            db_session.add(invoice)

        invoice = Invoice(
            invoice_number="20250115-3",
            client_id=None,
            issue_date=date(2025, 1, 15),
            status="draft",
        )
        db_session.add(invoice)
        await db_session.commit()

        num = await generate_invoice_number(db_session, date(2025, 1, 15))
        assert num == "20250115-4"


class TestDueDateCalculation:
    """Tests for due date calculation."""

    def test_explicit_due_date(self):
        issue = date(2025, 1, 15)
        due = date(2025, 2, 15)
        result = calculate_due_date(issue, explicit_due_date=due)
        assert result == due

    def test_invoice_terms_override(self, business_profile, client_record):
        issue = date(2025, 1, 15)
        result = calculate_due_date(
            issue, payment_terms_days=60, client=client_record, business=business_profile
        )
        assert result == issue + timedelta(days=60)

    def test_uses_client_terms(self, business_profile, client_record):
        issue = date(2025, 1, 15)
        result = calculate_due_date(issue, client=client_record, business=business_profile)
        assert result == issue + timedelta(days=30)

    def test_uses_business_default(self, business_profile):
        issue = date(2025, 1, 15)
        result = calculate_due_date(issue, client=None, business=business_profile)
        assert result == issue + timedelta(days=30)

    def test_fallback_to_thirty_days(self):
        issue = date(2025, 1, 15)
        result = calculate_due_date(issue, client=None, business=None)
        assert result == issue + timedelta(days=30)


class TestInvoiceTotals:
    """Tests for invoice total recalculation."""

    @pytest.mark.asyncio
    async def test_recalculate_empty_invoice(self, db_session):
        invoice = Invoice(
            invoice_number="20250115-1",
            issue_date=date.today(),
            status="draft",
        )
        db_session.add(invoice)
        await db_session.flush()

        await recalculate_invoice_totals(db_session, invoice)

        assert invoice.subtotal == Decimal("0")
        assert invoice.total == Decimal("0")

    @pytest.mark.asyncio
    async def test_recalculate_with_items(self, db_session):
        invoice = Invoice(
            invoice_number="20250115-1",
            issue_date=date.today(),
            status="draft",
        )
        db_session.add(invoice)
        await db_session.flush()

        item1 = InvoiceItem(
            invoice_id=invoice.id,
            description="Service 1",
            quantity=1,
            unit_price=Decimal("100.00"),
            total=Decimal("100.00"),
        )
        item2 = InvoiceItem(
            invoice_id=invoice.id,
            description="Service 2",
            quantity=2,
            unit_price=Decimal("50.00"),
            total=Decimal("100.00"),
        )
        db_session.add_all([item1, item2])
        await db_session.flush()

        await recalculate_invoice_totals(db_session, invoice)

        assert invoice.subtotal == Decimal("200")
        assert invoice.total == Decimal("200")


class TestClientSnapshot:
    """Tests for client info snapshotting."""

    @pytest.mark.asyncio
    async def test_snapshot_copies_client_fields(self, db_session, client_record):
        invoice = Invoice(
            invoice_number="20250115-1",
            client_id=client_record.id,
            issue_date=date.today(),
            status="draft",
        )
        db_session.add(invoice)
        await db_session.flush()

        snapshot_client_info(client_record, invoice)

        assert invoice.client_name == client_record.name
        assert invoice.client_business == client_record.business_name
        assert invoice.client_email == client_record.email
        assert client_record.city in invoice.client_address

    @pytest.mark.asyncio
    async def test_snapshot_with_minimal_client(self, db_session):
        client = Client(name="Minimal Client")
        db_session.add(client)
        await db_session.commit()

        invoice = Invoice(
            invoice_number="20250115-1",
            client_id=client.id,
            issue_date=date.today(),
            status="draft",
        )
        db_session.add(invoice)
        await db_session.flush()

        snapshot_client_info(client, invoice)

        assert invoice.client_name == "Minimal Client"
        assert invoice.client_business is None
        assert invoice.client_email is None


class TestFormatCurrency:
    """Tests for currency formatting."""

    def test_format_usd(self):
        assert format_currency(Decimal("1234.56")) == "$1,234.56"

    def test_format_zero(self):
        assert format_currency(Decimal("0")) == "$0.00"

    def test_format_large_number(self):
        assert format_currency(Decimal("1000000")) == "$1,000,000.00"

    def test_format_non_usd(self):
        assert format_currency(Decimal("500"), "EUR") == "500.00 EUR"

    def test_format_accepts_int_float_and_str(self):
        assert format_currency(100) == "$100.00"
        assert format_currency(1234.56) == "$1,234.56"
        assert format_currency("99.99") == "$99.99"
        assert format_currency(1000, "GBP") == "1,000.00 GBP"

    def test_format_negative(self):
        assert format_currency(-100) == "$-100.00"


class TestClientService:
    """Tests for ClientService."""

    @pytest.mark.asyncio
    async def test_list_clients_empty(self, db_session):
        clients = await ClientService.list_clients(db_session)
        assert clients == []

    @pytest.mark.asyncio
    async def test_list_clients_with_data(self, db_session, client_record):
        clients = await ClientService.list_clients(db_session)
        assert len(clients) == 1
        assert clients[0].id == client_record.id

    @pytest.mark.asyncio
    async def test_list_clients_excludes_deleted(self, db_session, client_record):
        client_record.deleted_at = date.today()
        await db_session.commit()

        clients = await ClientService.list_clients(db_session)
        assert len(clients) == 0

    @pytest.mark.asyncio
    async def test_list_clients_search(self, db_session, client_record):
        """Search filters by name or business name."""
        client_record.name = "John Smith"
        client_record.business_name = "Acme Corporation"
        await db_session.commit()

        results = await ClientService.list_clients(db_session, search="John")
        assert len(results) == 1

        results = await ClientService.list_clients(db_session, search="Acme")
        assert len(results) == 1

        results = await ClientService.list_clients(db_session, search="XYZ")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_create_client(self, db_session):
        client = await ClientService.create_client(
            db_session, name="Jane Doe", business_name="Jane's Company"
        )

        assert client.id is not None
        assert client.name == "Jane Doe"
        assert client.business_name == "Jane's Company"

    @pytest.mark.asyncio
    async def test_update_client(self, db_session, client_record):
        updated = await ClientService.update_client(
            db_session, client_record.id, name="Updated Name", phone="555-0000"
        )

        assert updated.name == "Updated Name"
        assert updated.phone == "555-0000"

    @pytest.mark.asyncio
    async def test_delete_client_soft(self, db_session, client_record):
        success = await ClientService.delete_client(db_session, client_record.id)
        assert success is True

        await db_session.refresh(client_record)
        assert client_record.deleted_at is not None

    @pytest.mark.asyncio
    async def test_restore_client(self, db_session, client_record):
        client_record.deleted_at = date.today()
        await db_session.commit()

        success = await ClientService.restore_client(db_session, client_record.id)
        assert success is True

        await db_session.refresh(client_record)
        assert client_record.deleted_at is None


class TestInvoiceService:
    """Tests for InvoiceService."""

    @pytest.mark.asyncio
    async def test_create_minimal_invoice(self, db_session, business_profile):
        invoice = await InvoiceService.create_invoice(db_session)

        assert invoice.id is not None
        assert invoice.invoice_number.startswith(utc_now().date().strftime("%Y%m%d"))
        assert invoice.status == "draft"
        assert invoice.currency_code == "USD"

    @pytest.mark.asyncio
    async def test_create_invoice_with_client(self, db_session, client_record):
        invoice = await InvoiceService.create_invoice(db_session, client_id=client_record.id)

        assert invoice.client_id == client_record.id
        assert invoice.client_name == client_record.name
        assert invoice.client_business == client_record.business_name

    @pytest.mark.asyncio
    async def test_create_invoice_with_items(self, db_session):
        invoice = await InvoiceService.create_invoice(
            db_session,
            items=[
                {"description": "Service 1", "quantity": 1, "unit_price": 100},
                {"description": "Service 2", "quantity": 2, "unit_price": 50},
            ],
        )

        assert len(invoice.items) == 2
        assert invoice.total == Decimal("200")

    @pytest.mark.asyncio
    async def test_create_invoice_backdated(self, db_session):
        invoice = await InvoiceService.create_invoice(db_session, issue_date=date(2024, 12, 15))

        assert invoice.invoice_number == "20241215-1"

    @pytest.mark.asyncio
    async def test_update_invoice_status(self, db_session, business_profile):
        invoice = await InvoiceService.create_invoice(db_session)

        updated = await InvoiceService.update_invoice(db_session, invoice.id, status="sent")

        assert updated.status == "sent"

    @pytest.mark.asyncio
    async def test_update_invoice_issue_date_changes_number(self, db_session):
        invoice = await InvoiceService.create_invoice(db_session)
        original_number = invoice.invoice_number

        updated = await InvoiceService.update_invoice(
            db_session, invoice.id, issue_date=date(2024, 12, 1)
        )

        assert updated.invoice_number != original_number
        assert updated.invoice_number.startswith("20241201")

    @pytest.mark.asyncio
    async def test_update_quote_issue_date_preserves_quote_prefix(self, db_session):
        """Backdating a quote keeps quote numbering instead of switching to invoice numbering."""
        quote = await InvoiceService.create_invoice(db_session, document_type="quote")

        updated = await InvoiceService.update_invoice(
            db_session, quote.id, issue_date=date(2024, 12, 1)
        )

        assert updated.document_type == "quote"
        assert updated.invoice_number.startswith("Q-20241201")

    @pytest.mark.asyncio
    async def test_delete_invoice_soft(self, db_session):
        invoice = await InvoiceService.create_invoice(db_session)

        success = await InvoiceService.delete_invoice(db_session, invoice.id)
        assert success is True

        await db_session.refresh(invoice)
        assert invoice.deleted_at is not None

    @pytest.mark.asyncio
    async def test_add_item_to_invoice(self, db_session):
        invoice = await InvoiceService.create_invoice(db_session)

        item = await InvoiceService.add_item(
            db_session, invoice.id, description="Test Service", quantity=1, unit_price=100
        )

        assert item.id is not None
        assert item.description == "Test Service"

        await db_session.refresh(invoice)
        assert invoice.total == Decimal("100")

    @pytest.mark.asyncio
    async def test_update_item(self, db_session):
        invoice = await InvoiceService.create_invoice(db_session)
        item = await InvoiceService.add_item(
            db_session, invoice.id, description="Original", quantity=1, unit_price=100
        )

        updated = await InvoiceService.update_item(
            db_session, item.id, description="Updated", quantity=2, unit_price=150
        )

        assert updated.description == "Updated"
        assert updated.quantity == 2
        assert updated.total == Decimal("300")

    @pytest.mark.asyncio
    async def test_remove_item(self, db_session):
        invoice = await InvoiceService.create_invoice(db_session)
        item = await InvoiceService.add_item(
            db_session, invoice.id, description="To Remove", quantity=1, unit_price=100
        )

        success = await InvoiceService.remove_item(db_session, item.id)
        assert success is True

        await db_session.refresh(invoice)
        assert invoice.total == Decimal("0")


class TestTrashPurge:
    """Tests for permanent trash cleanup behavior."""

    @pytest.mark.asyncio
    async def test_purge_trashed_records_keeps_client_with_active_invoice(
        self, db_session, client_record
    ):
        """Trashed clients are retained while any live invoice still references them."""
        invoice = await InvoiceService.create_invoice(db_session, client_id=client_record.id)
        client_record.deleted_at = date.today()
        await db_session.commit()

        result = await purge_trashed_records(db_session)
        await db_session.commit()

        assert result["clients_deleted"] == 0
        assert await db_session.get(Client, client_record.id) is not None
        assert await db_session.get(Invoice, invoice.id) is not None

    @pytest.mark.asyncio
    async def test_purge_trashed_records_deletes_invoice_items_before_invoices(
        self, db_session, client_record
    ):
        """Purging trashed invoices also removes their line items and then the now-unreferenced client."""
        invoice = await InvoiceService.create_invoice(
            db_session,
            client_id=client_record.id,
            items=[{"description": "Service", "quantity": 1, "unit_price": 100}],
        )
        invoice.deleted_at = date.today()
        client_record.deleted_at = date.today()
        await db_session.commit()

        result = await purge_trashed_records(db_session)
        await db_session.commit()

        item_count = int(
            (await db_session.execute(select(func.count(InvoiceItem.id)))).scalar() or 0
        )

        assert result["invoices_deleted"] == 1
        assert result["clients_deleted"] == 1
        assert await db_session.get(Invoice, invoice.id) is None
        assert await db_session.get(Client, client_record.id) is None
        assert item_count == 0


class TestPurgeDeletesGeneratedFiles:
    """Permanently deleting an invoice must not leave its PDF on disk."""

    @pytest.mark.asyncio
    async def test_purge_removes_pdf_files(self, db_session, tmp_path, monkeypatch):
        from invoice_machine.database import Invoice

        pdf_dir = tmp_path / "pdfs"
        pdf_dir.mkdir()
        doomed = pdf_dir / "doomed-1.pdf"
        doomed.write_bytes(b"%PDF-1.4")
        kept = pdf_dir / "kept-2.pdf"
        kept.write_bytes(b"%PDF-1.4")

        trashed = Invoice(
            invoice_number="TRASH-1",
            issue_date=date(2026, 1, 1),
            deleted_at=utc_now(),
            pdf_path="pdfs/doomed-1.pdf",
        )
        live = Invoice(
            invoice_number="LIVE-1",
            issue_date=date(2026, 1, 1),
            pdf_path="pdfs/kept-2.pdf",
        )
        db_session.add_all([trashed, live])
        await db_session.commit()

        monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
        result = await purge_trashed_records(db_session)
        await db_session.commit()

        assert result["invoices_deleted"] == 1
        assert result["pdfs_deleted"] == 1
        assert not doomed.exists(), "purged invoice's PDF should be gone"
        assert kept.exists(), "live invoice's PDF must be untouched"

    @pytest.mark.asyncio
    async def test_purge_ignores_path_traversal_in_stored_pdf_path(self, tmp_path, monkeypatch):
        """A crafted pdf_path must never delete outside the pdfs directory."""
        from invoice_machine.database import Invoice
        from invoice_machine.service.common import delete_invoice_pdf_files

        pdf_dir = tmp_path / "pdfs"
        pdf_dir.mkdir()
        outsider = tmp_path / "important.db"
        outsider.write_bytes(b"data")

        monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
        removed = delete_invoice_pdf_files(["../important.db", "pdfs/../../important.db"])

        assert removed == 0
        assert outsider.exists()
        assert Invoice is not None

    @pytest.mark.asyncio
    async def test_purge_clears_recurring_last_invoice_id(self, db_session, client_record):
        """A schedule pointing at a trashed invoice must not block the purge."""
        from invoice_machine.database import Invoice, RecurringSchedule

        invoice = Invoice(
            invoice_number="REC-1",
            issue_date=date(2026, 1, 1),
            client_id=client_record.id,
            deleted_at=utc_now(),
        )
        db_session.add(invoice)
        await db_session.commit()
        await db_session.refresh(invoice)

        schedule = RecurringSchedule(
            client_id=client_record.id,
            name="Retainer",
            frequency="monthly",
            schedule_day=1,
            next_invoice_date=date(2026, 2, 1),
            last_invoice_id=invoice.id,
        )
        db_session.add(schedule)
        await db_session.commit()

        result = await purge_trashed_records(db_session)
        await db_session.commit()
        assert result["invoices_deleted"] == 1

        await db_session.refresh(schedule)
        assert schedule.last_invoice_id is None

    @pytest.mark.asyncio
    async def test_purge_deletes_the_schedules_of_a_purged_client(self, db_session, client_record):
        """recurring_schedules.client_id is NOT NULL, so the schedule goes with the client."""
        from invoice_machine.database import RecurringSchedule

        schedule = RecurringSchedule(
            client_id=client_record.id,
            name="Retainer",
            frequency="monthly",
            schedule_day=1,
            next_invoice_date=date(2026, 2, 1),
        )
        db_session.add(schedule)
        client_record.deleted_at = utc_now()
        await db_session.commit()
        schedule_id = schedule.id

        result = await purge_trashed_records(db_session)
        await db_session.commit()

        assert result["clients_deleted"] == 1
        assert await db_session.get(RecurringSchedule, schedule_id) is None

    @pytest.mark.asyncio
    async def test_purging_the_converted_invoice_frees_the_quote(
        self, db_session, business_profile, client_record
    ):
        quote = await InvoiceService.create_invoice(
            db_session,
            client_id=client_record.id,
            document_type="quote",
            items=[{"description": "Proposal", "quantity": 1, "unit_price": 100}],
        )
        converted = await InvoiceService.convert_quote_to_invoice(db_session, quote.id)
        await InvoiceService.delete_invoice(db_session, converted.id)

        await purge_trashed_records(db_session)
        await db_session.commit()
        await db_session.refresh(quote)

        assert quote.converted_to_invoice_id is None
        assert await InvoiceService.convert_quote_to_invoice(db_session, quote.id) is not None

    @pytest.mark.asyncio
    async def test_purging_the_quote_clears_the_invoice_back_link(
        self, db_session, business_profile, client_record
    ):
        quote = await InvoiceService.create_invoice(
            db_session, client_id=client_record.id, document_type="quote"
        )
        converted = await InvoiceService.convert_quote_to_invoice(db_session, quote.id)
        await InvoiceService.delete_invoice(db_session, quote.id)

        await purge_trashed_records(db_session)
        await db_session.commit()
        await db_session.refresh(converted)

        assert converted.converted_from_invoice_id is None
