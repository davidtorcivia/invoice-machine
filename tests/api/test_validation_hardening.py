"""Regression tests for input validation and robustness at the API boundary."""

import pytest


@pytest.mark.asyncio
async def test_non_numeric_default_tax_rate_is_rejected(test_client):
    """A non-numeric tax rate must 422 at the schema, not 500 in the DB driver."""
    response = await test_client.put("/api/profile", json={"default_tax_rate": "abc"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_out_of_range_default_tax_rate_is_rejected(test_client):
    """A 999% default rate must be rejected, not silently applied to new invoices."""
    for bad_rate in ("999", "-5", "100.01"):
        response = await test_client.put("/api/profile", json={"default_tax_rate": bad_rate})
        assert response.status_code == 422, f"{bad_rate} should be rejected"

    ok = await test_client.put("/api/profile", json={"default_tax_rate": "8.25"})
    assert ok.status_code == 200
    assert ok.json()["default_tax_rate"] == "8.25"


@pytest.mark.asyncio
async def test_malformed_payment_methods_json_is_rejected(test_client):
    """Unparseable payment_methods must be rejected, not stored and read back as []."""
    response = await test_client.put("/api/profile", json={"payment_methods": "{not json at all"})
    assert response.status_code == 422

    response = await test_client.put("/api/profile", json={"payment_methods": '{"a": 1}'})
    assert response.status_code == 422, "must be a JSON array"

    response = await test_client.put("/api/profile", json={"payment_methods": '[{"name": "Bank"}]'})
    assert response.status_code == 422, "entries need an id"

    good = '[{"id": "pm-1", "name": "Bank Transfer", "instructions": "Acct 1"}]'
    response = await test_client.put("/api/profile", json={"payment_methods": good})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_add_item_to_missing_invoice_returns_404(test_client):
    """Adding a line item to a nonexistent invoice must 404, not 500 on the FK."""
    response = await test_client.post(
        "/api/invoices/999999/items",
        json={"description": "Service", "quantity": 1, "unit_price": "10"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_custom_invoice_number_returns_400(test_client):
    """A colliding invoice number is caller error, not a 500."""
    first = await test_client.post("/api/invoices", json={"invoice_number_override": "CUSTOM-1"})
    assert first.status_code in (200, 201)

    second = await test_client.post("/api/invoices", json={"invoice_number_override": "CUSTOM-1"})
    assert second.status_code == 400
    assert "already exists" in second.json()["detail"]


@pytest.mark.asyncio
async def test_pdf_endpoint_does_not_rerender_a_fresh_pdf(test_client, monkeypatch):
    """Fetching a PDF twice must render once."""
    renders = []

    async def fake_generate(session, invoice):
        renders.append(invoice.id)
        from invoice_machine.config import get_settings
        from invoice_machine.pdf.generator import invoice_pdf_filename

        settings = get_settings()
        settings.pdf_dir.mkdir(parents=True, exist_ok=True)
        name = invoice_pdf_filename(invoice)
        (settings.pdf_dir / name).write_bytes(b"%PDF-1.4 fake")
        return f"pdfs/{name}"

    monkeypatch.setattr("invoice_machine.pdf.generator.generate_pdf", fake_generate)

    created = await test_client.post(
        "/api/invoices",
        json={"items": [{"description": "Service", "quantity": 1, "unit_price": 100}]},
    )
    invoice_id = created.json()["id"]

    first = await test_client.get(f"/api/invoices/{invoice_id}/pdf")
    assert first.status_code == 200
    second = await test_client.get(f"/api/invoices/{invoice_id}/pdf")
    assert second.status_code == 200

    assert renders == [invoice_id], f"PDF should render once, rendered {len(renders)} times"


@pytest.mark.asyncio
async def test_recurring_rename_preserves_next_invoice_date(test_client):
    """Saving the schedule form unchanged must not move the billing date."""
    client = await test_client.post("/api/clients", json={"name": "Acme"})
    client_id = client.json()["id"]

    created = await test_client.post(
        "/api/recurring",
        json={
            "client_id": client_id,
            "name": "Retainer",
            "frequency": "monthly",
            "schedule_day": 15,
            "next_invoice_date": "2030-06-15",
        },
    )
    assert created.status_code == 201
    schedule_id = created.json()["id"]
    assert created.json()["next_invoice_date"] == "2030-06-15"

    # The UI always submits the whole form, cadence fields included.
    updated = await test_client.put(
        f"/api/recurring/{schedule_id}",
        json={"name": "Renamed", "frequency": "monthly", "schedule_day": 15},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["next_invoice_date"] == "2030-06-15"


@pytest.mark.asyncio
async def test_recurring_schedule_round_trips_yearly_month(test_client):
    """The yearly-month and quarter-month selectors must survive a round trip."""
    client = await test_client.post("/api/clients", json={"name": "Acme"})
    client_id = client.json()["id"]

    created = await test_client.post(
        "/api/recurring",
        json={
            "client_id": client_id,
            "name": "Annual licence",
            "frequency": "yearly",
            "schedule_day": 15,
            "schedule_month": 3,
            "auto_email_enabled": True,
            "show_payment_instructions": False,
            "selected_payment_methods": ["pm-1"],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["schedule_month"] == 3
    assert body["auto_email_enabled"] is True
    assert body["show_payment_instructions"] is False
    assert body["selected_payment_methods"] == ["pm-1"]


@pytest.mark.asyncio
async def test_recurring_schedule_rejects_unknown_client(test_client):
    """An unknown client must be a 400, not a 500 from the foreign key."""
    response = await test_client.post(
        "/api/recurring",
        json={"client_id": 999999, "name": "Orphan", "frequency": "monthly", "schedule_day": 1},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_invoice_response_exposes_payment_and_link_fields(test_client):
    """The REST response model must not silently strip new invoice fields.

    response_model=InvoiceSchema filters the serialized dict, so a field missing
    from the schema disappears from every invoice response.
    """
    created = await test_client.post(
        "/api/invoices",
        json={"items": [{"description": "Service", "quantity": 1, "unit_price": 100}]},
    )
    assert created.status_code in (200, 201)
    body = created.json()

    for field in (
        "amount_paid",
        "amount_due",
        "is_partially_paid",
        "exchange_rate",
        "base_currency_code",
        "converted_from_invoice_id",
        "converted_to_invoice_id",
        "payment_link_url",
        "reminders_sent",
    ):
        assert field in body, f"{field} missing from the invoice response"

    fetched = await test_client.get(f"/api/invoices/{body['id']}")
    assert "amount_due" in fetched.json()


@pytest.mark.asyncio
async def test_converted_invoice_response_carries_the_quote_link(test_client):
    """The convert endpoint must report which quote the invoice came from."""
    quote = await test_client.post(
        "/api/invoices",
        json={
            "document_type": "quote",
            "items": [{"description": "Design", "quantity": 1, "unit_price": 500}],
        },
    )
    quote_id = quote.json()["id"]

    converted = await test_client.post(f"/api/invoices/{quote_id}/convert", json={})
    assert converted.status_code == 201
    assert converted.json()["converted_from_invoice_id"] == quote_id

    quote_after = await test_client.get(f"/api/invoices/{quote_id}")
    assert quote_after.json()["converted_to_invoice_id"] == converted.json()["id"]
