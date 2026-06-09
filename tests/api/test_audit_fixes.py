"""Regression tests for the 2026-06 audit fixes."""

import pytest


@pytest.mark.asyncio
async def test_create_invoice_without_tax_enabled_inherits_business_default(test_client):
    """Omitting tax_enabled on REST create must inherit the business default, not
    force tax off (the schema default used to be 0)."""
    await test_client.put(
        "/api/profile",
        json={"default_tax_enabled": True, "default_tax_rate": "10"},
    )

    response = await test_client.post(
        "/api/invoices",
        json={"items": [{"description": "Service", "quantity": 1, "unit_price": 500}]},
    )
    assert response.status_code in (200, 201)
    data = response.json()
    assert data["tax_enabled"] is True
    assert data["tax_amount"] == "50.00"
    assert data["total"] == "550.00"


@pytest.mark.asyncio
async def test_add_item_endpoint_accepts_fractional_quantity(test_client):
    """The add-item endpoint must accept fractional quantities (e.g. 1.5 hours)."""
    invoice = await test_client.post(
        "/api/invoices",
        json={"items": [{"description": "Base", "quantity": 1, "unit_price": 100}]},
    )
    invoice_id = invoice.json()["id"]

    response = await test_client.post(
        f"/api/invoices/{invoice_id}/items",
        params={
            "description": "Consulting",
            "quantity": 1.5,
            "unit_type": "hours",
            "unit_price": 100,
        },
    )
    assert response.status_code == 201
    item = response.json()
    assert item["quantity"] == "1.5"
    assert item["total"] == "150.00"


@pytest.mark.asyncio
async def test_invoice_unit_price_must_be_numeric(test_client):
    """A non-numeric unit_price is rejected at the schema (422), not a 500."""
    response = await test_client.post(
        "/api/invoices",
        json={"items": [{"description": "x", "quantity": 1, "unit_price": "abc"}]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_paid_at_is_serialized(test_client):
    """paid_at is exposed once an invoice is marked paid (and cleared otherwise)."""
    invoice = await test_client.post(
        "/api/invoices",
        json={"items": [{"description": "x", "quantity": 1, "unit_price": 100}]},
    )
    invoice_id = invoice.json()["id"]
    assert invoice.json()["paid_at"] is None

    paid = await test_client.put(f"/api/invoices/{invoice_id}", json={"status": "paid"})
    assert paid.json()["paid_at"] is not None

    unpaid = await test_client.put(f"/api/invoices/{invoice_id}", json={"status": "sent"})
    assert unpaid.json()["paid_at"] is None
