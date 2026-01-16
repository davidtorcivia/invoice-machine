"""Tests for business logic services."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from invoicely.database import Client, Invoice, InvoiceItem, BusinessProfile
from invoicely.services import (
    generate_invoice_number,
    calculate_due_date,
    recalculate_invoice_totals,
    snapshot_client_info,
    format_currency,
    ClientService,
    InvoiceService,
)


class TestInvoiceNumberGeneration:
    """Tests for invoice number generation."""

    @pytest.mark.asyncio
    async def test_first_invoice_of_day(self, db_session):
        """First invoice gets sequence 1."""
        num = await generate_invoice_number(db_session, date(2025, 1, 15))
        assert num == "20250115-1"

    @pytest.mark.asyncio
    async def test_second_invoice_of_day(self, db_session):
        """Second invoice gets sequence 2."""
        # Create first invoice
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
        """Different day resets sequence to 1."""
        # Create invoice on previous day
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
        """Ignores malformed invoice numbers when calculating sequence."""
        # Create malformed invoices
        for num in ["20250115-bad", "not-a-number", "20250115-"]:
            invoice = Invoice(
                invoice_number=num,
                client_id=None,
                issue_date=date(2025, 1, 15),
                status="draft",
            )
            db_session.add(invoice)

        # Create one valid
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
        """Explicit due date takes precedence."""
        issue = date(2025, 1, 15)
        due = date(2025, 2, 15)
        result = calculate_due_date(issue, explicit_due_date=due)
        assert result == due

    def test_invoice_terms_override(self, business_profile, test_client):
        """Invoice terms override client terms."""
        issue = date(2025, 1, 15)
        result = calculate_due_date(
            issue, payment_terms_days=60, client=test_client, business=business_profile
        )
        assert result == issue + timedelta(days=60)

    def test_uses_client_terms(self, business_profile, test_client):
        """Uses client terms when no invoice terms."""
        issue = date(2025, 1, 15)
        result = calculate_due_date(issue, client=test_client, business=business_profile)
        assert result == issue + timedelta(days=30)

    def test_uses_business_default(self, business_profile):
        """Uses business default when no client terms."""
        issue = date(2025, 1, 15)
        result = calculate_due_date(issue, client=None, business=business_profile)
        assert result == issue + timedelta(days=30)

    def test_fallback_to_thirty_days(self):
        """Falls back to 30 days when nothing specified."""
        issue = date(2025, 1, 15)
        result = calculate_due_date(issue, client=None, business=None)
        assert result == issue + timedelta(days=30)


class TestInvoiceTotals:
    """Tests for invoice total recalculation."""

    @pytest.mark.asyncio
    async def test_recalculate_empty_invoice(self, db_session):
        """Empty invoice has zero totals."""
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
        """Recalculates totals from line items."""
        invoice = Invoice(
            invoice_number="20250115-1",
            issue_date=date.today(),
            status="draft",
        )
        db_session.add(invoice)
        await db_session.flush()

        # Add items
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
    async def test_snapshot_copies_client_fields(self, db_session, test_client):
        """Snapshot copies relevant client fields to invoice."""
        invoice = Invoice(
            invoice_number="20250115-1",
            client_id=test_client.id,
            issue_date=date.today(),
            status="draft",
        )
        db_session.add(invoice)
        await db_session.flush()

        await snapshot_client_info(db_session, test_client, invoice)

        assert invoice.client_name == test_client.name
        assert invoice.client_business == test_client.business_name
        assert invoice.client_email == test_client.email
        assert test_client.city in invoice.client_address

    @pytest.mark.asyncio
    async def test_snapshot_with_minimal_client(self, db_session):
        """Snapshot handles client with minimal info."""
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

        await snapshot_client_info(db_session, client, invoice)

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


class TestClientService:
    """Tests for ClientService."""

    @pytest.mark.asyncio
    async def test_list_clients_empty(self, db_session):
        """Listing with no clients returns empty list."""
        clients = await ClientService.list_clients(db_session)
        assert clients == []

    @pytest.mark.asyncio
    async def test_list_clients_with_data(self, db_session, test_client):
        """Lists all active clients."""
        clients = await ClientService.list_clients(db_session)
        assert len(clients) == 1
        assert clients[0].id == test_client.id

    @pytest.mark.asyncio
    async def test_list_clients_excludes_deleted(self, db_session, test_client):
        """Soft-deleted clients excluded by default."""
        test_client.deleted_at = date.today()
        await db_session.commit()

        clients = await ClientService.list_clients(db_session)
        assert len(clients) == 0

    @pytest.mark.asyncio
    async def test_list_clients_search(self, db_session, test_client):
        """Search filters by name or business name."""
        test_client.name = "John Smith"
        test_client.business_name = "Acme Corporation"
        await db_session.commit()

        # Search by name
        results = await ClientService.list_clients(db_session, search="John")
        assert len(results) == 1

        # Search by business
        results = await ClientService.list_clients(db_session, search="Acme")
        assert len(results) == 1

        # No match
        results = await ClientService.list_clients(db_session, search="XYZ")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_create_client(self, db_session):
        """Creates a new client."""
        client = await ClientService.create_client(
            db_session, name="Jane Doe", business_name="Jane's Company"
        )

        assert client.id is not None
        assert client.name == "Jane Doe"
        assert client.business_name == "Jane's Company"

    @pytest.mark.asyncio
    async def test_update_client(self, db_session, test_client):
        """Updates client fields."""
        updated = await ClientService.update_client(
            db_session, test_client.id, name="Updated Name", phone="555-0000"
        )

        assert updated.name == "Updated Name"
        assert updated.phone == "555-0000"

    @pytest.mark.asyncio
    async def test_delete_client_soft(self, db_session, test_client):
        """Delete is a soft delete."""
        success = await ClientService.delete_client(db_session, test_client.id)
        assert success is True

        # Refresh from DB
        await db_session.refresh(test_client)
        assert test_client.deleted_at is not None

    @pytest.mark.asyncio
    async def test_restore_client(self, db_session, test_client):
        """Restores a soft-deleted client."""
        test_client.deleted_at = date.today()
        await db_session.commit()

        success = await ClientService.restore_client(db_session, test_client.id)
        assert success is True

        await db_session.refresh(test_client)
        assert test_client.deleted_at is None


class TestInvoiceService:
    """Tests for InvoiceService."""

    @pytest.mark.asyncio
    async def test_create_minimal_invoice(self, db_session, business_profile):
        """Creates invoice with minimal data."""
        invoice = await InvoiceService.create_invoice(db_session)

        assert invoice.id is not None
        assert invoice.invoice_number.startswith(date.today().strftime("%Y%m%d"))
        assert invoice.status == "draft"
        assert invoice.currency_code == "USD"

    @pytest.mark.asyncio
    async def test_create_invoice_with_client(self, db_session, test_client):
        """Creates invoice linked to client."""
        invoice = await InvoiceService.create_invoice(db_session, client_id=test_client.id)

        assert invoice.client_id == test_client.id
        assert invoice.client_name == test_client.name
        assert invoice.client_business == test_client.business_name

    @pytest.mark.asyncio
    async def test_create_invoice_with_items(self, db_session):
        """Creates invoice with line items."""
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
        """Backdated invoice gets correct number."""
        invoice = await InvoiceService.create_invoice(
            db_session, issue_date=date(2024, 12, 15)
        )

        assert invoice.invoice_number == "20241215-1"

    @pytest.mark.asyncio
    async def test_update_invoice_status(self, db_session, business_profile):
        """Updates invoice status."""
        invoice = await InvoiceService.create_invoice(db_session)

        updated = await InvoiceService.update_invoice(
            db_session, invoice.id, status="sent"
        )

        assert updated.status == "sent"

    @pytest.mark.asyncio
    async def test_update_invoice_issue_date_changes_number(self, db_session):
        """Changing issue date regenerates invoice number."""
        invoice = await InvoiceService.create_invoice(db_session)
        original_number = invoice.invoice_number

        updated = await InvoiceService.update_invoice(
            db_session, invoice.id, issue_date=date(2024, 12, 1)
        )

        assert updated.invoice_number != original_number
        assert updated.invoice_number.startswith("20241201")

    @pytest.mark.asyncio
    async def test_delete_invoice_soft(self, db_session):
        """Delete is a soft delete."""
        invoice = await InvoiceService.create_invoice(db_session)

        success = await InvoiceService.delete_invoice(db_session, invoice.id)
        assert success is True

        await db_session.refresh(invoice)
        assert invoice.deleted_at is not None

    @pytest.mark.asyncio
    async def test_add_item_to_invoice(self, db_session):
        """Adds line item to invoice."""
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
        """Updates line item."""
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
        """Removes line item."""
        invoice = await InvoiceService.create_invoice(db_session)
        item = await InvoiceService.add_item(
            db_session, invoice.id, description="To Remove", quantity=1, unit_price=100
        )

        success = await InvoiceService.remove_item(db_session, item.id)
        assert success is True

        await db_session.refresh(invoice)
        assert invoice.total == Decimal("0")
