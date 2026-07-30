"""HTTP-level tests for recording payments, focused on retry safety.

The service layer is covered in tests/test_payments.py. These exercise the one
thing only the endpoint owns: the optional ``Idempotency-Key`` header, which is
what stops a double-submitted form from recording a payment twice.
"""

import pytest


async def _sent_invoice(test_client, unit_price="100.00"):
    """Create an invoice and move it out of draft so it can take payments."""
    created = await test_client.post(
        "/api/invoices",
        json={"items": [{"description": "Work", "quantity": 1, "unit_price": unit_price}]},
    )
    assert created.status_code in (200, 201), created.text
    invoice_id = created.json()["id"]

    await test_client.put(f"/api/invoices/{invoice_id}", json={"status": "sent"})
    return invoice_id


@pytest.mark.asyncio
async def test_payment_api_honours_idempotency_key(test_client):
    """A double-submitted form must not record the payment twice.

    Uses a partial payment on purpose: a repeated *full* payment was already
    rejected by the outstanding-balance check, so it would pass regardless of
    whether the key works.
    """
    invoice_id = await _sent_invoice(test_client)

    request = {
        "json": {"amount": "40.00"},
        "headers": {"Idempotency-Key": "payment-api-retry-1"},
    }
    first = await test_client.post(f"/api/invoices/{invoice_id}/payments", **request)
    second = await test_client.post(f"/api/invoices/{invoice_id}/payments", **request)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    detail = await test_client.get(f"/api/invoices/{invoice_id}")
    assert detail.json()["amount_paid"] == "40.00", "the retry was counted twice"


@pytest.mark.asyncio
async def test_payment_api_still_works_without_a_key(test_client):
    """The header is optional so the existing UI keeps working."""
    invoice_id = await _sent_invoice(test_client, unit_price="10.00")

    response = await test_client.post(
        f"/api/invoices/{invoice_id}/payments", json={"amount": "10.00"}
    )
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_distinct_keys_record_separate_payments(test_client):
    """Two real payments of the same amount are still both recorded."""
    invoice_id = await _sent_invoice(test_client)

    for key in ("instalment-aaa", "instalment-bbb"):
        response = await test_client.post(
            f"/api/invoices/{invoice_id}/payments",
            json={"amount": "40.00"},
            headers={"Idempotency-Key": key},
        )
        assert response.status_code == 201, response.text

    detail = await test_client.get(f"/api/invoices/{invoice_id}")
    assert detail.json()["amount_paid"] == "80.00"


@pytest.mark.asyncio
async def test_payment_api_rejects_a_too_short_key(test_client):
    """A key too short to be unique is a caller error, not a silent no-op."""
    invoice_id = await _sent_invoice(test_client, unit_price="10.00")

    response = await test_client.post(
        f"/api/invoices/{invoice_id}/payments",
        json={"amount": "10.00"},
        headers={"Idempotency-Key": "short"},
    )
    assert response.status_code == 400
    assert "8-255" in response.json()["detail"]
