"""Tests for FastAPI endpoints."""

from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient, ASGITransport

from invoicely.main import app
from invoicely.database import Base, BusinessProfile, Client
from invoicely.services import InvoiceService


@pytest.fixture(scope="function")
async def test_client():
    """Test client for HTTP requests."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session maker with test engine
    import invoicely.database
    original_maker = invoicely.database.async_session_maker
    invoicely.database.async_session_maker = async_sessionmaker(
        engine, expire_on_commit=False
    )

    # Create business profile
    async with invoicely.database.async_session_maker() as session:
        profile = BusinessProfile(
            id=1,
            name="Test Business",
            business_name="Test LLC",
            email="test@example.com",
        )
        session.add(profile)
        await session.commit()

    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    # Restore original
    invoicely.database.async_session_maker = original_maker
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
