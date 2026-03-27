from datetime import date, timedelta

import pytest


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
    async def test_get_dashboard_summary_excludes_quotes(self, test_client):
        """Dashboard summary only counts invoice documents."""
        paid_invoice = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "invoice",
                "items": [{"description": "Paid invoice", "quantity": 1, "unit_price": 500}],
            },
        )
        sent_invoice = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "invoice",
                "items": [{"description": "Sent invoice", "quantity": 1, "unit_price": 200}],
            },
        )
        draft_invoice = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "invoice",
                "items": [{"description": "Draft invoice", "quantity": 1, "unit_price": 50}],
            },
        )
        paid_quote = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "quote",
                "items": [{"description": "Paid quote", "quantity": 1, "unit_price": 900}],
            },
        )

        await test_client.put(
            f"/api/invoices/{paid_invoice.json()['id']}",
            json={"status": "paid"},
        )
        await test_client.put(
            f"/api/invoices/{sent_invoice.json()['id']}",
            json={"status": "sent"},
        )
        await test_client.put(
            f"/api/invoices/{draft_invoice.json()['id']}",
            json={"status": "draft"},
        )
        await test_client.put(
            f"/api/invoices/{paid_quote.json()['id']}",
            json={"status": "paid"},
        )

        response = await test_client.get("/api/analytics/dashboard")
        assert response.status_code == 200

        data = response.json()
        assert data["total_outstanding"] == "200.00"
        assert data["paid_this_month"] == "500.00"
        assert data["draft_count"] == 1
        assert data["invoice_count"] == 3

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
    async def test_get_revenue_excludes_quotes_from_invoice_totals(self, test_client):
        """Revenue analytics ignore quote amounts even after quote status changes."""
        issue_date = date.today().isoformat()

        paid_invoice = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "invoice",
                "issue_date": issue_date,
                "items": [{"description": "Paid invoice", "quantity": 1, "unit_price": 500}],
            },
        )
        sent_invoice = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "invoice",
                "issue_date": issue_date,
                "items": [{"description": "Sent invoice", "quantity": 1, "unit_price": 200}],
            },
        )
        paid_quote = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "quote",
                "issue_date": issue_date,
                "items": [{"description": "Paid quote", "quantity": 1, "unit_price": 900}],
            },
        )
        sent_quote = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "quote",
                "issue_date": issue_date,
                "items": [{"description": "Sent quote", "quantity": 1, "unit_price": 800}],
            },
        )

        await test_client.put(
            f"/api/invoices/{paid_invoice.json()['id']}",
            json={"status": "paid"},
        )
        await test_client.put(
            f"/api/invoices/{sent_invoice.json()['id']}",
            json={"status": "sent"},
        )
        await test_client.put(
            f"/api/invoices/{paid_quote.json()['id']}",
            json={"status": "paid"},
        )
        await test_client.put(
            f"/api/invoices/{sent_quote.json()['id']}",
            json={"status": "sent"},
        )

        response = await test_client.get("/api/analytics/revenue")
        assert response.status_code == 200

        data = response.json()
        assert data["totals"]["invoiced"] == "700.00"
        assert data["totals"]["paid"] == "500.00"
        assert data["totals"]["outstanding"] == "200.00"
        assert data["totals"]["invoice_count"] == 2
        assert len(data["breakdown"]) == 1
        assert data["breakdown"][0]["invoiced"] == "700.00"
        assert data["breakdown"][0]["paid"] == "500.00"
        assert data["breakdown"][0]["count"] == 2

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
    async def test_get_revenue_outstanding_and_overdue_not_filtered_by_date(self, test_client):
        """Outstanding and overdue totals include invoices from all years."""
        today = date.today()
        last_year = f"{today.year - 1}-06-15"
        this_year = f"{today.year}-03-01"

        # Create an overdue invoice from last year
        old_invoice = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "invoice",
                "issue_date": last_year,
                "items": [{"description": "Old overdue", "quantity": 1, "unit_price": 9000}],
            },
        )
        await test_client.put(
            f"/api/invoices/{old_invoice.json()['id']}",
            json={"status": "overdue"},
        )

        # Create an overdue invoice from this year
        new_invoice = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "invoice",
                "issue_date": this_year,
                "items": [{"description": "New overdue", "quantity": 1, "unit_price": 1200}],
            },
        )
        await test_client.put(
            f"/api/invoices/{new_invoice.json()['id']}",
            json={"status": "overdue"},
        )

        # Query revenue for this year only
        response = await test_client.get(
            f"/api/analytics/revenue?from_date={today.year}-01-01&to_date={today.year}-12-31"
        )
        assert response.status_code == 200
        data = response.json()

        # Period-scoped metrics should only include this year's invoice
        assert data["totals"]["invoiced"] == "1200.00"

        # Point-in-time metrics should include BOTH invoices
        assert data["totals"]["outstanding"] == "10200.00"
        assert data["totals"]["overdue"] == "10200.00"

    @pytest.mark.asyncio
    async def test_get_revenue_sent_past_due_counted_as_overdue(self, test_client):
        """Sent invoices past their due date are counted as overdue in reports."""
        today = date.today()
        past_due_date = (today - timedelta(days=10)).isoformat()
        issue_date = (today - timedelta(days=40)).isoformat()

        # Create invoice with status "sent" but past its due date
        sent_past_due = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "invoice",
                "issue_date": issue_date,
                "due_date": past_due_date,
                "items": [{"description": "Past due work", "quantity": 1, "unit_price": 5000}],
            },
        )
        await test_client.put(
            f"/api/invoices/{sent_past_due.json()['id']}",
            json={"status": "sent"},
        )

        # Create invoice with explicit overdue status
        explicitly_overdue = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "invoice",
                "issue_date": issue_date,
                "due_date": past_due_date,
                "items": [{"description": "Overdue work", "quantity": 1, "unit_price": 3000}],
            },
        )
        await test_client.put(
            f"/api/invoices/{explicitly_overdue.json()['id']}",
            json={"status": "overdue"},
        )

        response = await test_client.get("/api/analytics/revenue")
        assert response.status_code == 200
        data = response.json()

        # Both should count as outstanding
        assert data["totals"]["outstanding"] == "8000.00"
        # Both should count as overdue (sent+past_due and explicit overdue)
        assert data["totals"]["overdue"] == "8000.00"

    @pytest.mark.asyncio
    async def test_update_invoice_tax_recalculates_total(self, test_client):
        """Updating tax settings on an invoice recalculates the total."""
        invoice = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "invoice",
                "items": [{"description": "Service", "quantity": 1, "unit_price": 1000}],
            },
        )
        invoice_data = invoice.json()
        assert invoice_data["total"] == "1000.00"

        # Enable 10% tax
        updated = await test_client.put(
            f"/api/invoices/{invoice_data['id']}",
            json={"tax_enabled": 1, "tax_rate": 10},
        )
        updated_data = updated.json()
        assert updated_data["total"] == "1100.00"
        assert updated_data["tax_amount"] == "100.00"

        # Disable tax
        updated2 = await test_client.put(
            f"/api/invoices/{invoice_data['id']}",
            json={"tax_enabled": 0},
        )
        updated2_data = updated2.json()
        assert updated2_data["total"] == "1000.00"
        assert updated2_data["tax_amount"] == "0.00"

    @pytest.mark.asyncio
    async def test_get_revenue_sent_not_yet_due_not_overdue(self, test_client):
        """Sent invoices NOT past due should be outstanding but NOT overdue."""
        today = date.today()
        future_due_date = (today + timedelta(days=30)).isoformat()

        sent_not_due = await test_client.post(
            "/api/invoices",
            json={
                "document_type": "invoice",
                "issue_date": today.isoformat(),
                "due_date": future_due_date,
                "items": [{"description": "Not yet due", "quantity": 1, "unit_price": 2000}],
            },
        )
        await test_client.put(
            f"/api/invoices/{sent_not_due.json()['id']}",
            json={"status": "sent"},
        )

        response = await test_client.get("/api/analytics/revenue")
        assert response.status_code == 200
        data = response.json()

        # Should count as outstanding but NOT overdue
        assert data["totals"]["outstanding"] == "2000.00"
        assert data["totals"]["overdue"] == "0.00"

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
    async def test_get_client_lifetime_values_excludes_quotes(self, test_client):
        """Client lifetime value only counts invoice documents."""
        client_response = await test_client.post(
            "/api/clients", json={"name": "Invoice-only Client"}
        )
        client_id = client_response.json()["id"]

        invoice_response = await test_client.post(
            "/api/invoices",
            json={
                "client_id": client_id,
                "document_type": "invoice",
                "items": [{"description": "Invoice work", "quantity": 1, "unit_price": 500}],
            },
        )
        quote_response = await test_client.post(
            "/api/invoices",
            json={
                "client_id": client_id,
                "document_type": "quote",
                "items": [{"description": "Quoted work", "quantity": 1, "unit_price": 900}],
            },
        )

        await test_client.put(
            f"/api/invoices/{invoice_response.json()['id']}",
            json={"status": "paid"},
        )
        await test_client.put(
            f"/api/invoices/{quote_response.json()['id']}",
            json={"status": "paid"},
        )

        response = await test_client.get(f"/api/analytics/clients?client_id={client_id}")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["total_invoiced"] == "500.00"
        assert data[0]["total_paid"] == "500.00"
        assert data[0]["invoice_count"] == 1
        assert data[0]["paid_invoice_count"] == 1

    @pytest.mark.asyncio
    async def test_get_client_lifetime_values_with_limit(self, test_client):
        """Get client lifetime values with limit."""
        response = await test_client.get("/api/analytics/clients?limit=5")
        assert response.status_code == 200

        data = response.json()
        assert len(data) <= 5

    @pytest.mark.asyncio
    async def test_get_client_lifetime_values_limit_uses_top_paid_clients(self, test_client):
        """Client LTV limit is applied after sorting by paid revenue."""
        clients = []
        for name in ["Lower", "Highest", "Middle"]:
            response = await test_client.post("/api/clients", json={"name": name})
            clients.append(response.json())

        amounts = [100, 900, 500]
        for client, amount in zip(clients, amounts):
            invoice_response = await test_client.post(
                "/api/invoices",
                json={
                    "client_id": client["id"],
                    "document_type": "invoice",
                    "items": [{"description": client["name"], "quantity": 1, "unit_price": amount}],
                },
            )
            await test_client.put(
                f"/api/invoices/{invoice_response.json()['id']}",
                json={"status": "paid"},
            )

        quote_response = await test_client.post(
            "/api/invoices",
            json={
                "client_id": clients[0]["id"],
                "document_type": "quote",
                "items": [{"description": "Ignored quote", "quantity": 1, "unit_price": 5000}],
            },
        )
        await test_client.put(
            f"/api/invoices/{quote_response.json()['id']}",
            json={"status": "paid"},
        )

        response = await test_client.get("/api/analytics/clients?limit=2")
        assert response.status_code == 200

        data = response.json()
        assert [client["name"] for client in data] == ["Highest", "Middle"]
        assert [client["total_paid"] for client in data] == ["900.00", "500.00"]



