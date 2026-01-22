"""Tests for FastAPI endpoints."""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from invoice_machine.main import app
from invoice_machine.database import Base, BusinessProfile, Client, User
from invoice_machine.services import InvoiceService
from invoice_machine.api.auth import create_session, SESSION_COOKIE_NAME


@pytest_asyncio.fixture(scope="function")
async def test_client():
    """Test client for HTTP requests with authentication."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    import bcrypt

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session maker with test engine
    import invoice_machine.database
    original_maker = invoice_machine.database.async_session_maker
    invoice_machine.database.async_session_maker = async_sessionmaker(
        engine, expire_on_commit=False
    )

    # Create business profile and test user
    async with invoice_machine.database.async_session_maker() as session:
        profile = BusinessProfile(
            id=1,
            name="Test Business",
            business_name="Test LLC",
            email="test@example.com",
        )
        session.add(profile)

        # Create test user
        password_hash = bcrypt.hashpw("testpass".encode(), bcrypt.gensalt()).decode()
        user = User(
            id=1,
            username="testuser",
            password_hash=password_hash,
        )
        session.add(user)
        await session.commit()

    # Create session token
    session_token = create_session(user_id=1)

    # Create client with session cookie
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    client.cookies.set(SESSION_COOKIE_NAME, session_token)

    yield client

    # Restore original
    invoice_machine.database.async_session_maker = original_maker
    await engine.dispose()


class TestHealthEndpoint:
    """Tests for health check."""

    @pytest.mark.asyncio
    async def test_health_check(self, test_client):
        """Health check returns 200."""
        response = await test_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestProfileEndpoints:
    """Tests for business profile endpoints."""

    @pytest.mark.asyncio
    async def test_get_profile(self, test_client):
        """Get business profile."""
        response = await test_client.get("/api/profile")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Test Business"
        assert data["business_name"] == "Test LLC"

    @pytest.mark.asyncio
    async def test_update_profile(self, test_client):
        """Update business profile."""
        response = await test_client.put(
            "/api/profile", json={"name": "Updated Name", "phone": "555-1234"}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["phone"] == "555-1234"

    @pytest.mark.asyncio
    async def test_partial_update(self, test_client):
        """Partial update only changes provided fields."""
        response = await test_client.put("/api/profile", json={"phone": "555-9999"})
        assert response.status_code == 200

        # Name should be unchanged
        data = response.json()
        assert data["name"] == "Test Business"
        assert data["phone"] == "555-9999"


class TestClientEndpoints:
    """Tests for client endpoints."""

    @pytest.mark.asyncio
    async def test_list_clients_empty(self, test_client):
        """List clients returns empty list initially."""
        response = await test_client.get("/api/clients")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_create_client(self, test_client):
        """Create a new client."""
        response = await test_client.post(
            "/api/clients",
            json={
                "name": "John Doe",
                "business_name": "Acme Corp",
                "email": "john@acme.com",
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["id"] > 0
        assert data["name"] == "John Doe"
        assert data["business_name"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_create_minimal_client(self, test_client):
        """Create client with minimal data."""
        response = await test_client.post(
            "/api/clients", json={"business_name": "Minimal Corp"}
        )
        assert response.status_code == 201

        data = response.json()
        assert data["business_name"] == "Minimal Corp"

    @pytest.mark.asyncio
    async def test_get_client(self, test_client):
        """Get client by ID."""
        # First create a client
        create_response = await test_client.post(
            "/api/clients", json={"name": "Jane Doe", "email": "jane@example.com"}
        )
        client_id = create_response.json()["id"]

        # Get the client
        response = await test_client.get(f"/api/clients/{client_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == client_id
        assert data["name"] == "Jane Doe"

    @pytest.mark.asyncio
    async def test_get_nonexistent_client(self, test_client):
        """Getting nonexistent client returns 404."""
        response = await test_client.get("/api/clients/99999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_client(self, test_client):
        """Update client."""
        # Create a client
        create_response = await test_client.post(
            "/api/clients", json={"name": "Original Name"}
        )
        client_id = create_response.json()["id"]

        # Update it
        response = await test_client.put(
            f"/api/clients/{client_id}", json={"name": "Updated Name", "phone": "555-0000"}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["phone"] == "555-0000"

    @pytest.mark.asyncio
    async def test_delete_client(self, test_client):
        """Delete client (soft delete)."""
        # Create a client
        create_response = await test_client.post(
            "/api/clients", json={"name": "To Delete"}
        )
        client_id = create_response.json()["id"]

        # Delete it
        response = await test_client.delete(f"/api/clients/{client_id}")
        assert response.status_code == 204

        # Should not appear in normal list
        list_response = await test_client.get("/api/clients")
        assert list_response.json() == []

    @pytest.mark.asyncio
    async def test_restore_client(self, test_client):
        """Restore deleted client."""
        # Create and delete a client
        create_response = await test_client.post(
            "/api/clients", json={"name": "To Restore"}
        )
        client_id = create_response.json()["id"]

        await test_client.delete(f"/api/clients/{client_id}")

        # Restore it
        response = await test_client.post(f"/api/clients/{client_id}/restore")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == client_id
        assert data["deleted_at"] is None


class TestInvoiceEndpoints:
    """Tests for invoice endpoints."""

    @pytest.mark.asyncio
    async def test_list_invoices_empty(self, test_client):
        """List invoices returns empty list initially."""
        response = await test_client.get("/api/invoices")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_create_invoice(self, test_client):
        """Create a new invoice."""
        response = await test_client.post(
            "/api/invoices",
            json={
                "currency_code": "USD",
                "notes": "Payment due within 30 days.",
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["id"] > 0
        assert data["status"] == "draft"
        assert data["currency_code"] == "USD"

    @pytest.mark.asyncio
    async def test_create_invoice_with_items(self, test_client):
        """Create invoice with line items."""
        response = await test_client.post(
            "/api/invoices",
            json={
                "items": [
                    {"description": "Service 1", "quantity": 1, "unit_price": 100},
                    {"description": "Service 2", "quantity": 2, "unit_price": 50},
                ]
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == "200.00"

    @pytest.mark.asyncio
    async def test_create_invoice_with_client(self, test_client):
        """Create invoice linked to client."""
        # First create a client
        client_response = await test_client.post(
            "/api/clients", json={"name": "Bill To", "business_name": "Client Corp"}
        )
        client_id = client_response.json()["id"]

        # Create invoice with client
        response = await test_client.post(
            "/api/invoices", json={"client_id": client_id}
        )
        assert response.status_code == 201

        data = response.json()
        assert data["client_id"] == client_id
        assert data["client_business"] == "Client Corp"

    @pytest.mark.asyncio
    async def test_get_invoice(self, test_client):
        """Get invoice by ID."""
        # Create an invoice
        create_response = await test_client.post("/api/invoices", json={})
        invoice_id = create_response.json()["id"]

        # Get the invoice
        response = await test_client.get(f"/api/invoices/{invoice_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == invoice_id

    @pytest.mark.asyncio
    async def test_update_invoice_status(self, test_client):
        """Update invoice status."""
        # Create an invoice
        create_response = await test_client.post("/api/invoices", json={})
        invoice_id = create_response.json()["id"]

        # Update status
        response = await test_client.put(
            f"/api/invoices/{invoice_id}", json={"status": "sent"}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "sent"

    @pytest.mark.asyncio
    async def test_update_invoice_backdate(self, test_client):
        """Backdating invoice changes invoice number."""
        # Create an invoice
        create_response = await test_client.post("/api/invoices", json={})
        original_number = create_response.json()["invoice_number"]
        invoice_id = create_response.json()["id"]

        # Backdate to December
        response = await test_client.put(
            f"/api/invoices/{invoice_id}", json={"issue_date": "2024-12-01"}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["invoice_number"] != original_number
        assert data["invoice_number"].startswith("20241201")

    @pytest.mark.asyncio
    async def test_delete_invoice(self, test_client):
        """Delete invoice (soft delete)."""
        # Create an invoice
        create_response = await test_client.post("/api/invoices", json={})
        invoice_id = create_response.json()["id"]

        # Delete it
        response = await test_client.delete(f"/api/invoices/{invoice_id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_add_invoice_item(self, test_client):
        """Add line item to invoice."""
        # Create an invoice
        create_response = await test_client.post("/api/invoices", json={})
        invoice_id = create_response.json()["id"]

        # Add item
        response = await test_client.post(
            f"/api/invoices/{invoice_id}/items",
            params={
                "description": "New Service",
                "quantity": 1,
                "unit_price": "150.00",
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["description"] == "New Service"
        assert data["total"] == "150.00"

    @pytest.mark.asyncio
    async def test_update_invoice_item(self, test_client):
        """Update line item."""
        # Create invoice with item
        create_response = await test_client.post(
            "/api/invoices",
            json={"items": [{"description": "Original", "quantity": 1, "unit_price": 100}]},
        )
        invoice_id = create_response.json()["id"]
        item_id = create_response.json()["items"][0]["id"]

        # Update item
        response = await test_client.put(
            f"/api/invoices/{invoice_id}/items/{item_id}",
            json={"description": "Updated", "quantity": 2, "unit_price": 75},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["description"] == "Updated"
        assert data["total"] == "150.00"

    @pytest.mark.asyncio
    async def test_delete_invoice_item(self, test_client):
        """Delete line item."""
        # Create invoice with item
        create_response = await test_client.post(
            "/api/invoices",
            json={"items": [{"description": "To Delete", "quantity": 1, "unit_price": 100}]},
        )
        invoice_id = create_response.json()["id"]
        item_id = create_response.json()["items"][0]["id"]

        # Delete item
        response = await test_client.delete(f"/api/invoices/{invoice_id}/items/{item_id}")
        assert response.status_code == 204

        # Check invoice total is now 0
        get_response = await test_client.get(f"/api/invoices/{invoice_id}")
        assert get_response.json()["total"] == "0.00"


class TestTrashEndpoints:
    """Tests for trash endpoints."""

    @pytest.mark.asyncio
    async def test_list_trash_empty(self, test_client):
        """Trash is empty initially."""
        response = await test_client.get("/api/trash")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_trash_with_items(self, test_client):
        """Lists both trashed clients and invoices."""
        # Create and delete a client
        client_response = await test_client.post(
            "/api/clients", json={"name": "Deleted Client"}
        )
        client_id = client_response.json()["id"]
        await test_client.delete(f"/api/clients/{client_id}")

        # Create and delete an invoice
        invoice_response = await test_client.post("/api/invoices", json={})
        invoice_id = invoice_response.json()["id"]
        await test_client.delete(f"/api/invoices/{invoice_id}")

        # List trash
        response = await test_client.get("/api/trash")
        assert response.status_code == 200

        items = response.json()
        assert len(items) == 2

        types = {item["type"] for item in items}
        assert "client" in types
        assert "invoice" in types


class TestRecurringEndpoints:
    """Tests for recurring invoice schedule endpoints."""

    @pytest.mark.asyncio
    async def test_list_recurring_empty(self, test_client):
        """List recurring schedules returns empty list initially."""
        response = await test_client.get("/api/recurring")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_create_recurring_schedule(self, test_client):
        """Create a recurring schedule."""
        # First create a client
        client_response = await test_client.post(
            "/api/clients", json={"name": "Recurring Client"}
        )
        client_id = client_response.json()["id"]

        # Create recurring schedule
        response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "Monthly Retainer",
                "frequency": "monthly",
                "schedule_day": 1,
                "line_items": [
                    {"description": "Retainer Fee", "quantity": 1, "unit_type": "qty", "unit_price": "500.00"}
                ],
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["id"] > 0
        assert data["name"] == "Monthly Retainer"
        assert data["frequency"] == "monthly"
        assert data["schedule_day"] == 1
        assert data["is_active"] == 1

    @pytest.mark.asyncio
    async def test_get_recurring_schedule(self, test_client):
        """Get a recurring schedule by ID."""
        # Create client and schedule
        client_response = await test_client.post(
            "/api/clients", json={"name": "Test Client"}
        )
        client_id = client_response.json()["id"]

        create_response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "Test Schedule",
                "frequency": "weekly",
                "schedule_day": 0,
            },
        )
        schedule_id = create_response.json()["id"]

        # Get it
        response = await test_client.get(f"/api/recurring/{schedule_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == schedule_id
        assert data["name"] == "Test Schedule"

    @pytest.mark.asyncio
    async def test_get_nonexistent_schedule(self, test_client):
        """Getting nonexistent schedule returns 404."""
        response = await test_client.get("/api/recurring/99999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_recurring_schedule(self, test_client):
        """Update a recurring schedule."""
        # Create client and schedule
        client_response = await test_client.post(
            "/api/clients", json={"name": "Test Client"}
        )
        client_id = client_response.json()["id"]

        create_response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "Original Name",
                "frequency": "monthly",
                "schedule_day": 15,
            },
        )
        schedule_id = create_response.json()["id"]

        # Update it
        response = await test_client.put(
            f"/api/recurring/{schedule_id}",
            json={"name": "Updated Name", "schedule_day": 20},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["schedule_day"] == 20

    @pytest.mark.asyncio
    async def test_pause_schedule(self, test_client):
        """Pause a recurring schedule."""
        # Create client and schedule
        client_response = await test_client.post(
            "/api/clients", json={"name": "Test Client"}
        )
        client_id = client_response.json()["id"]

        create_response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "To Pause",
                "frequency": "monthly",
            },
        )
        schedule_id = create_response.json()["id"]

        # Pause it
        response = await test_client.post(f"/api/recurring/{schedule_id}/pause")
        assert response.status_code == 200

        data = response.json()
        assert data["is_active"] == 0

    @pytest.mark.asyncio
    async def test_resume_schedule(self, test_client):
        """Resume a paused schedule."""
        # Create client and schedule
        client_response = await test_client.post(
            "/api/clients", json={"name": "Test Client"}
        )
        client_id = client_response.json()["id"]

        create_response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "To Resume",
                "frequency": "monthly",
            },
        )
        schedule_id = create_response.json()["id"]

        # Pause then resume
        await test_client.post(f"/api/recurring/{schedule_id}/pause")
        response = await test_client.post(f"/api/recurring/{schedule_id}/resume")
        assert response.status_code == 200

        data = response.json()
        assert data["is_active"] == 1

    @pytest.mark.asyncio
    async def test_trigger_schedule(self, test_client):
        """Manually trigger a recurring schedule."""
        # Create client and schedule
        client_response = await test_client.post(
            "/api/clients", json={"name": "Trigger Client"}
        )
        client_id = client_response.json()["id"]

        create_response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "To Trigger",
                "frequency": "monthly",
                "schedule_day": 1,
                "line_items": [
                    {"description": "Service", "quantity": 1, "unit_type": "qty", "unit_price": "100.00"}
                ],
            },
        )
        schedule_id = create_response.json()["id"]

        # Trigger it
        response = await test_client.post(f"/api/recurring/{schedule_id}/trigger")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "invoice_id" in data
        assert "invoice_number" in data

    @pytest.mark.asyncio
    async def test_delete_schedule(self, test_client):
        """Delete a recurring schedule."""
        # Create client and schedule
        client_response = await test_client.post(
            "/api/clients", json={"name": "Delete Client"}
        )
        client_id = client_response.json()["id"]

        create_response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "To Delete",
                "frequency": "monthly",
            },
        )
        schedule_id = create_response.json()["id"]

        # Delete it
        response = await test_client.delete(f"/api/recurring/{schedule_id}")
        assert response.status_code == 204

        # Verify deleted
        get_response = await test_client.get(f"/api/recurring/{schedule_id}")
        assert get_response.status_code == 404


class TestSearchEndpoints:
    """Tests for search API endpoints."""

    @pytest.mark.asyncio
    async def test_search_empty_query(self, test_client):
        """Empty search query returns empty results."""
        response = await test_client.get("/api/search?q=")
        assert response.status_code == 200

        data = response.json()
        assert data["invoices"] == []
        assert data["clients"] == []

    @pytest.mark.asyncio
    async def test_search_clients_by_name(self, test_client):
        """Search finds clients by name."""
        # Create a client
        await test_client.post(
            "/api/clients", json={"name": "UniqueSearchName", "business_name": "Search Corp"}
        )

        # Search for it
        response = await test_client.get("/api/search?q=UniqueSearchName")
        assert response.status_code == 200

        data = response.json()
        assert len(data["clients"]) >= 1
        assert any("UniqueSearchName" in c.get("name", "") for c in data["clients"])

    @pytest.mark.asyncio
    async def test_search_invoices(self, test_client):
        """Search finds invoices by number."""
        # Create an invoice
        create_response = await test_client.post("/api/invoices", json={})
        invoice_number = create_response.json()["invoice_number"]

        # Search for it (first 8 chars should be date-based)
        search_term = invoice_number[:8]
        response = await test_client.get(f"/api/search?q={search_term}")
        assert response.status_code == 200

        data = response.json()
        # Should find the invoice
        assert "invoices" in data

    @pytest.mark.asyncio
    async def test_search_with_limit(self, test_client):
        """Search respects limit parameter."""
        # Create multiple clients
        for i in range(5):
            await test_client.post(
                "/api/clients", json={"name": f"LimitTest{i}", "business_name": "Limit Corp"}
            )

        # Search with limit
        response = await test_client.get("/api/search?q=LimitTest&limit=2")
        assert response.status_code == 200

        data = response.json()
        assert len(data["clients"]) <= 2


class TestEmailEndpoints:
    """Tests for email/SMTP API endpoints."""

    @pytest.mark.asyncio
    async def test_get_smtp_settings_empty(self, test_client):
        """Get SMTP settings when not configured."""
        response = await test_client.get("/api/settings/smtp")
        assert response.status_code == 200

        data = response.json()
        assert "smtp_host" in data
        assert "smtp_enabled" in data

    @pytest.mark.asyncio
    async def test_update_smtp_settings(self, test_client):
        """Update SMTP settings."""
        response = await test_client.put(
            "/api/settings/smtp",
            json={
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_username": "user@example.com",
                "smtp_password": "secret123",
                "smtp_use_tls": True,
                "smtp_from_email": "invoices@example.com",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["smtp_host"] == "smtp.example.com"
        assert data["smtp_port"] == 587
        # Password is never exposed, only smtp_password_set indicates if it's set
        assert data["smtp_password_set"] is True

    @pytest.mark.asyncio
    async def test_get_smtp_password_set_flag(self, test_client):
        """SMTP password presence is indicated by smtp_password_set flag."""
        # Set password
        await test_client.put(
            "/api/settings/smtp",
            json={"smtp_password": "mysecretpassword"},
        )

        # Get settings
        response = await test_client.get("/api/settings/smtp")
        assert response.status_code == 200

        data = response.json()
        # Password should never be returned, only the flag
        assert data["smtp_password_set"] is True
        assert "smtp_password" not in data

    @pytest.mark.asyncio
    async def test_send_invoice_email_no_smtp(self, test_client):
        """Sending invoice email without SMTP configured fails gracefully."""
        # Create an invoice
        create_response = await test_client.post("/api/invoices", json={})
        invoice_id = create_response.json()["id"]

        # Try to send email (should fail - no SMTP configured)
        response = await test_client.post(
            f"/api/invoices/{invoice_id}/send-email",
            json={"recipient_email": "test@example.com"},
        )
        # Should return 400 - SMTP not enabled
        assert response.status_code == 400


class TestAnalyticsEndpoints:
    """Tests for analytics API endpoints."""

    @pytest.mark.asyncio
    async def test_get_revenue_empty(self, test_client):
        """Get revenue analytics with no invoices."""
        response = await test_client.get("/api/analytics/revenue")
        assert response.status_code == 200

        data = response.json()
        assert "totals" in data
        assert "breakdown" in data

    @pytest.mark.asyncio
    async def test_get_revenue_with_invoices(self, test_client):
        """Get revenue analytics with invoices."""
        # Create an invoice with items
        await test_client.post(
            "/api/invoices",
            json={
                "status": "paid",
                "items": [{"description": "Service", "quantity": 1, "unit_price": 100}],
            },
        )

        # Get analytics
        response = await test_client.get("/api/analytics/revenue")
        assert response.status_code == 200

        data = response.json()
        assert "totals" in data
        assert data["totals"]["invoiced"] is not None

    @pytest.mark.asyncio
    async def test_get_revenue_with_date_filter(self, test_client):
        """Get revenue analytics with date filter."""
        response = await test_client.get(
            "/api/analytics/revenue?from_date=2025-01-01&to_date=2025-12-31"
        )
        assert response.status_code == 200

        data = response.json()
        assert "totals" in data

    @pytest.mark.asyncio
    async def test_get_revenue_group_by_month(self, test_client):
        """Get revenue analytics grouped by month."""
        response = await test_client.get("/api/analytics/revenue?group_by=month")
        assert response.status_code == 200

        data = response.json()
        assert "breakdown" in data

    @pytest.mark.asyncio
    async def test_get_revenue_group_by_quarter(self, test_client):
        """Get revenue analytics grouped by quarter."""
        response = await test_client.get("/api/analytics/revenue?group_by=quarter")
        assert response.status_code == 200

        data = response.json()
        assert "breakdown" in data

    @pytest.mark.asyncio
    async def test_get_client_lifetime_values_empty(self, test_client):
        """Get client lifetime values with no data."""
        response = await test_client.get("/api/analytics/clients")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_client_lifetime_values_with_data(self, test_client):
        """Get client lifetime values with paid invoices."""
        # Create a client
        client_response = await test_client.post(
            "/api/clients", json={"name": "LTV Client"}
        )
        client_id = client_response.json()["id"]

        # Create a paid invoice for the client
        await test_client.post(
            "/api/invoices",
            json={
                "client_id": client_id,
                "status": "paid",
                "items": [{"description": "Service", "quantity": 1, "unit_price": 500}],
            },
        )

        # Get client LTV
        response = await test_client.get("/api/analytics/clients")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        # Should have the client in results
        if len(data) > 0:
            assert "name" in data[0]
            assert "total_paid" in data[0] or "total_invoiced" in data[0]

    @pytest.mark.asyncio
    async def test_get_client_lifetime_values_with_limit(self, test_client):
        """Get client lifetime values with limit."""
        response = await test_client.get("/api/analytics/clients?limit=5")
        assert response.status_code == 200

        data = response.json()
        assert len(data) <= 5


class TestTaxSettingsEndpoints:
    """Tests for tax settings in profile API."""

    @pytest.mark.asyncio
    async def test_get_profile_includes_tax_settings(self, test_client):
        """Profile response includes tax settings."""
        response = await test_client.get("/api/profile")
        assert response.status_code == 200

        data = response.json()
        assert "default_tax_enabled" in data
        assert "default_tax_rate" in data
        assert "default_tax_name" in data

    @pytest.mark.asyncio
    async def test_update_tax_settings(self, test_client):
        """Update tax settings via profile."""
        response = await test_client.put(
            "/api/profile",
            json={
                "default_tax_enabled": True,
                "default_tax_rate": "8.25",
                "default_tax_name": "Sales Tax",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["default_tax_enabled"] is True
        assert data["default_tax_rate"] == "8.25"
        assert data["default_tax_name"] == "Sales Tax"
