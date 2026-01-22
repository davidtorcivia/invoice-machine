"""Tests for new features: tax handling, recurring invoices, and search."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from invoice_machine.database import Client, Invoice, BusinessProfile, RecurringSchedule
from invoice_machine.services import (
    ClientService,
    InvoiceService,
    RecurringService,
    SearchService,
)


class TestTaxCascade:
    """Tests for tax settings cascade (invoice > client > global)."""

    @pytest.mark.asyncio
    async def test_tax_from_global_default(self, db_session, business_profile):
        """Invoice uses global tax settings when no overrides."""
        # Set global tax settings
        business_profile.default_tax_enabled = 1
        business_profile.default_tax_rate = Decimal("8.25")
        business_profile.default_tax_name = "Sales Tax"
        await db_session.commit()

        invoice = await InvoiceService.create_invoice(
            db_session,
            items=[{"description": "Service", "quantity": 1, "unit_price": 100}],
        )

        assert invoice.tax_enabled == 1
        assert invoice.tax_rate == Decimal("8.25")
        assert invoice.tax_name == "Sales Tax"
        assert invoice.tax_amount == Decimal("8.25")
        assert invoice.total == Decimal("108.25")

    @pytest.mark.asyncio
    async def test_tax_from_client_override(self, db_session, business_profile, test_client):
        """Invoice uses client tax settings when set."""
        # Set global defaults
        business_profile.default_tax_enabled = 1
        business_profile.default_tax_rate = Decimal("8.25")
        await db_session.commit()

        # Set client override
        test_client.tax_enabled = 1
        test_client.tax_rate = Decimal("10.00")
        test_client.tax_name = "VAT"
        await db_session.commit()

        invoice = await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            items=[{"description": "Service", "quantity": 1, "unit_price": 100}],
        )

        assert invoice.tax_rate == Decimal("10.00")
        assert invoice.tax_name == "VAT"
        assert invoice.tax_amount == Decimal("10.00")
        assert invoice.total == Decimal("110.00")

    @pytest.mark.asyncio
    async def test_tax_from_invoice_param_override(self, db_session, business_profile, test_client):
        """Invoice parameter overrides both client and global."""
        # Set global and client defaults
        business_profile.default_tax_enabled = 1
        business_profile.default_tax_rate = Decimal("8.25")
        test_client.tax_rate = Decimal("10.00")
        await db_session.commit()

        invoice = await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            tax_enabled=True,
            tax_rate=Decimal("5.00"),
            tax_name="Special Tax",
            items=[{"description": "Service", "quantity": 1, "unit_price": 100}],
        )

        assert invoice.tax_rate == Decimal("5.00")
        assert invoice.tax_name == "Special Tax"
        assert invoice.tax_amount == Decimal("5.00")
        assert invoice.total == Decimal("105.00")

    @pytest.mark.asyncio
    async def test_tax_disabled_no_tax_applied(self, db_session, business_profile):
        """No tax applied when tax is disabled."""
        business_profile.default_tax_enabled = 0
        business_profile.default_tax_rate = Decimal("8.25")
        await db_session.commit()

        invoice = await InvoiceService.create_invoice(
            db_session,
            items=[{"description": "Service", "quantity": 1, "unit_price": 100}],
        )

        assert invoice.tax_enabled == 0
        assert invoice.tax_amount == Decimal("0.00")
        assert invoice.total == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_tax_rate_validation(self, db_session, business_profile):
        """Tax rate must be between 0 and 100."""
        with pytest.raises(ValueError, match="Tax rate must be between 0 and 100"):
            await InvoiceService.create_invoice(
                db_session,
                tax_enabled=True,
                tax_rate=Decimal("150.00"),
            )

        with pytest.raises(ValueError, match="Tax rate must be between 0 and 100"):
            await InvoiceService.create_invoice(
                db_session,
                tax_enabled=True,
                tax_rate=Decimal("-5.00"),
            )


class TestRecurringInvoices:
    """Tests for recurring invoice schedules."""

    @pytest.mark.asyncio
    async def test_create_monthly_schedule(self, db_session, test_client):
        """Create a monthly recurring schedule."""
        schedule = await RecurringService.create_schedule(
            db_session,
            client_id=test_client.id,
            name="Monthly Retainer",
            frequency="monthly",
            schedule_day=15,
            line_items=[{"description": "Retainer", "quantity": 1, "unit_price": 500}],
        )

        assert schedule.id is not None
        assert schedule.name == "Monthly Retainer"
        assert schedule.frequency == "monthly"
        assert schedule.schedule_day == 15
        assert schedule.is_active == 1

    @pytest.mark.asyncio
    async def test_create_weekly_schedule(self, db_session, test_client):
        """Create a weekly recurring schedule."""
        schedule = await RecurringService.create_schedule(
            db_session,
            client_id=test_client.id,
            name="Weekly Report",
            frequency="weekly",
            schedule_day=0,  # Monday
            line_items=[{"description": "Weekly Report", "quantity": 1, "unit_price": 100}],
        )

        assert schedule.frequency == "weekly"
        assert schedule.schedule_day == 0

    @pytest.mark.asyncio
    async def test_invalid_frequency(self, db_session, test_client):
        """Invalid frequency raises error."""
        with pytest.raises(ValueError, match="Invalid frequency"):
            await RecurringService.create_schedule(
                db_session,
                client_id=test_client.id,
                name="Invalid",
                frequency="biweekly",
            )

    @pytest.mark.asyncio
    async def test_invalid_schedule_day_weekly(self, db_session, test_client):
        """Invalid schedule_day for weekly raises error."""
        with pytest.raises(ValueError, match="schedule_day must be 0-6"):
            await RecurringService.create_schedule(
                db_session,
                client_id=test_client.id,
                name="Invalid",
                frequency="weekly",
                schedule_day=7,
            )

    @pytest.mark.asyncio
    async def test_invalid_schedule_day_monthly(self, db_session, test_client):
        """Invalid schedule_day for monthly raises error."""
        with pytest.raises(ValueError, match="schedule_day must be 1-31"):
            await RecurringService.create_schedule(
                db_session,
                client_id=test_client.id,
                name="Invalid",
                frequency="monthly",
                schedule_day=32,
            )

    @pytest.mark.asyncio
    async def test_trigger_schedule(self, db_session, business_profile, test_client):
        """Manually trigger a schedule creates invoice."""
        schedule = await RecurringService.create_schedule(
            db_session,
            client_id=test_client.id,
            name="Test Schedule",
            frequency="monthly",
            schedule_day=1,
            line_items=[{"description": "Service", "quantity": 1, "unit_price": 100}],
        )

        result = await RecurringService.trigger_schedule(db_session, schedule.id)

        assert result["success"] is True
        assert "invoice_id" in result
        assert "invoice_number" in result

        # Verify invoice was created
        invoice = await InvoiceService.get_invoice(db_session, result["invoice_id"])
        assert invoice is not None
        assert invoice.client_id == test_client.id
        assert invoice.total == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_pause_and_resume_schedule(self, db_session, test_client):
        """Pause and resume a schedule."""
        schedule = await RecurringService.create_schedule(
            db_session,
            client_id=test_client.id,
            name="Test",
            frequency="monthly",
        )

        # Pause
        success = await RecurringService.pause_schedule(db_session, schedule.id)
        assert success is True
        await db_session.refresh(schedule)
        assert schedule.is_active == 0

        # Resume
        success = await RecurringService.resume_schedule(db_session, schedule.id)
        assert success is True
        await db_session.refresh(schedule)
        assert schedule.is_active == 1

    @pytest.mark.asyncio
    async def test_list_schedules_active_only(self, db_session, test_client):
        """List schedules filters by active status."""
        # Create active schedule
        active = await RecurringService.create_schedule(
            db_session,
            client_id=test_client.id,
            name="Active",
            frequency="monthly",
        )

        # Create and pause another
        paused = await RecurringService.create_schedule(
            db_session,
            client_id=test_client.id,
            name="Paused",
            frequency="monthly",
        )
        await RecurringService.pause_schedule(db_session, paused.id)

        # List active only
        schedules = await RecurringService.list_schedules(db_session, active_only=True)
        assert len(schedules) == 1
        assert schedules[0].name == "Active"

        # List all
        schedules = await RecurringService.list_schedules(db_session, active_only=False)
        assert len(schedules) == 2

    @pytest.mark.asyncio
    async def test_delete_schedule(self, db_session, test_client):
        """Delete a schedule."""
        schedule = await RecurringService.create_schedule(
            db_session,
            client_id=test_client.id,
            name="To Delete",
            frequency="monthly",
        )
        schedule_id = schedule.id

        success = await RecurringService.delete_schedule(db_session, schedule_id)
        assert success is True

        # Verify deleted
        deleted = await RecurringService.get_schedule(db_session, schedule_id)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_calculate_next_date_monthly(self, db_session):
        """Calculate next date for monthly frequency."""
        current = date(2025, 1, 15)
        next_date = RecurringService.calculate_next_date(current, "monthly", 15)
        assert next_date == date(2025, 2, 15)

    @pytest.mark.asyncio
    async def test_calculate_next_date_handles_month_end(self, db_session):
        """Calculate next date handles months with fewer days."""
        current = date(2025, 1, 31)
        next_date = RecurringService.calculate_next_date(current, "monthly", 31)
        # February doesn't have 31 days, should use last day
        assert next_date.month == 2
        assert next_date.day == 28


class TestSearch:
    """Tests for FTS5 search functionality."""

    @pytest.mark.asyncio
    async def test_search_clients_by_name(self, db_session, test_client):
        """Search finds clients by name."""
        test_client.name = "John Doe"
        test_client.business_name = "Acme Corporation"
        await db_session.commit()

        results = await SearchService.search(db_session, "John")
        assert len(results["clients"]) >= 1

    @pytest.mark.asyncio
    async def test_search_clients_by_business_name(self, db_session, test_client):
        """Search finds clients by business name."""
        test_client.business_name = "Acme Corporation"
        await db_session.commit()

        results = await SearchService.search(db_session, "Acme")
        # May use fallback LIKE search if FTS5 not available
        assert len(results["clients"]) >= 1

    @pytest.mark.asyncio
    async def test_search_invoices_by_number(self, db_session, business_profile):
        """Search finds invoices by invoice number."""
        invoice = await InvoiceService.create_invoice(db_session)
        invoice_number = invoice.invoice_number

        results = await SearchService.search(db_session, invoice_number[:8])
        assert len(results["invoices"]) >= 1

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(self, db_session):
        """Empty query returns empty results."""
        results = await SearchService.search(db_session, "")
        assert results == {"invoices": [], "clients": [], "line_items": []}

        results = await SearchService.search(db_session, "   ")
        assert results == {"invoices": [], "clients": [], "line_items": []}

    @pytest.mark.asyncio
    async def test_search_limit_respected(self, db_session, business_profile):
        """Search limit is respected."""
        # Create multiple invoices
        for i in range(5):
            await InvoiceService.create_invoice(db_session)

        results = await SearchService.search(db_session, "20", limit=2)
        assert len(results["invoices"]) <= 2

    @pytest.mark.asyncio
    async def test_search_limit_clamped(self, db_session):
        """Search limit is clamped to reasonable bounds."""
        # Should not error with extreme limits
        results = await SearchService.search(db_session, "test", limit=10000)
        # Limit should be clamped to 100
        assert isinstance(results, dict)

        results = await SearchService.search(db_session, "test", limit=-5)
        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_search_sanitizes_special_characters(self, db_session):
        """Search sanitizes FTS5 special characters."""
        # These should not cause errors
        results = await SearchService.search(db_session, 'test"injection')
        assert isinstance(results, dict)

        results = await SearchService.search(db_session, "test*wildcard")
        assert isinstance(results, dict)

        results = await SearchService.search(db_session, "test AND OR NOT")
        assert isinstance(results, dict)

        results = await SearchService.search(db_session, "test(parentheses)")
        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_search_only_invoices(self, db_session, test_client):
        """Search can be limited to invoices only."""
        results = await SearchService.search(
            db_session, "test", search_invoices=True, search_clients=False
        )
        assert "invoices" in results
        # Clients should still be in results but empty since we didn't search
        assert results["clients"] == []

    @pytest.mark.asyncio
    async def test_search_only_clients(self, db_session, test_client):
        """Search can be limited to clients only."""
        results = await SearchService.search(
            db_session, "test", search_invoices=False, search_clients=True
        )
        assert "clients" in results
        assert results["invoices"] == []

    @pytest.mark.asyncio
    async def test_search_line_items_by_description(self, db_session, business_profile):
        """Search finds line items by description."""
        # Create a client
        client = await ClientService.create_client(
            db_session, name="Line Item Test Client"
        )
        # Create an invoice with a specific line item description
        invoice = await InvoiceService.create_invoice(
            db_session,
            client_id=client.id,
            items=[{"description": "Custom Widget Development", "quantity": 1, "unit_price": 500}],
        )

        # Search for the line item
        results = await SearchService.search(db_session, "Widget")
        assert "line_items" in results
        assert len(results["line_items"]) >= 1
        assert any("Widget" in item["description"] for item in results["line_items"])

        # Verify line item has invoice context
        matching_item = next(
            item for item in results["line_items"] if "Widget" in item["description"]
        )
        assert matching_item["invoice_id"] == invoice.id
        assert matching_item["invoice_number"] == invoice.invoice_number
        assert matching_item["client_name"] == "Line Item Test Client"

    @pytest.mark.asyncio
    async def test_search_only_line_items(self, db_session, business_profile):
        """Search can be limited to line items only."""
        # Create a client
        client = await ClientService.create_client(
            db_session, name="Line Items Only Client"
        )
        # Create an invoice with a line item
        await InvoiceService.create_invoice(
            db_session,
            client_id=client.id,
            items=[{"description": "Unique Search Term XYZ", "quantity": 1, "unit_price": 100}],
        )

        # Search with only line_items
        results = await SearchService.search(
            db_session, "XYZ", search_invoices=False, search_clients=False, search_line_items=True
        )
        assert results["invoices"] == []
        assert results["clients"] == []
        assert len(results["line_items"]) >= 1

    @pytest.mark.asyncio
    async def test_search_excludes_line_items(self, db_session, business_profile):
        """Search can exclude line items."""
        # Create a client
        client = await ClientService.create_client(
            db_session, name="Exclude Line Items Client"
        )
        # Create an invoice with a line item
        await InvoiceService.create_invoice(
            db_session,
            client_id=client.id,
            items=[{"description": "Excluded Item ABC", "quantity": 1, "unit_price": 100}],
        )

        # Search without line_items
        results = await SearchService.search(
            db_session, "ABC", search_invoices=True, search_clients=True, search_line_items=False
        )
        assert results["line_items"] == []


class TestClientTaxSettings:
    """Tests for per-client tax settings."""

    @pytest.mark.asyncio
    async def test_client_with_tax_override(self, db_session):
        """Create client with tax override settings."""
        client = await ClientService.create_client(
            db_session,
            name="Tax Client",
            tax_enabled=1,
            tax_rate=Decimal("7.50"),
            tax_name="State Tax",
        )

        assert client.tax_enabled == 1
        assert client.tax_rate == Decimal("7.50")
        assert client.tax_name == "State Tax"

    @pytest.mark.asyncio
    async def test_update_client_tax_settings(self, db_session, test_client):
        """Update client tax settings."""
        updated = await ClientService.update_client(
            db_session,
            test_client.id,
            tax_enabled=1,
            tax_rate=Decimal("5.00"),
        )

        assert updated.tax_enabled == 1
        assert updated.tax_rate == Decimal("5.00")

    @pytest.mark.asyncio
    async def test_client_null_tax_uses_global(self, db_session, business_profile, test_client):
        """Client with null tax settings uses global default."""
        business_profile.default_tax_enabled = 1
        business_profile.default_tax_rate = Decimal("8.00")
        await db_session.commit()

        # Client has no tax override (None)
        assert test_client.tax_enabled is None

        invoice = await InvoiceService.create_invoice(
            db_session,
            client_id=test_client.id,
            items=[{"description": "Service", "quantity": 1, "unit_price": 100}],
        )

        # Should use global default
        assert invoice.tax_rate == Decimal("8.00")
