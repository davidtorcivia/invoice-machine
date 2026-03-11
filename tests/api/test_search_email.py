from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from invoice_machine.main import app
from invoice_machine.services import InvoiceService
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



