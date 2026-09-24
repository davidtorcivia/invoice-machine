"""The permanent pay link: admin creation and the public /pay page."""

from urllib.parse import parse_qs

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from invoice_machine.main import app
from invoice_machine.service import stripe_links

CHECKOUT_URL = "https://checkout.stripe.com/c/pay/cs_test_1"


@pytest.fixture
def stripe_requests(monkeypatch):
    """Answer Stripe's Checkout API locally and record what was sent."""
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"id": "cs_test_1", "url": CHECKOUT_URL})

    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        return real_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(stripe_links.httpx, "AsyncClient", fake_client)
    return sent


async def _payable_invoice(test_client, *, base_url="https://inv.example"):
    await test_client.put("/api/profile", json={"app_base_url": base_url})
    settings = await test_client.put(
        "/api/settings/payments",
        json={"payments_enabled": True, "stripe_secret_key": "sk_test_x"},
    )
    assert settings.status_code == 200, settings.text
    created = await test_client.post(
        "/api/invoices",
        json={"items": [{"description": "Work", "quantity": 1, "unit_price": "100.00"}]},
    )
    invoice_id = created.json()["id"]
    await test_client.put(f"/api/invoices/{invoice_id}", json={"status": "sent"})
    return invoice_id


def _public_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_link_is_permanent_and_checkout_returns_to_the_pay_page(test_client, stripe_requests):
    invoice_id = await _payable_invoice(test_client)

    first = await test_client.post(f"/api/invoices/{invoice_id}/payment-link")
    second = await test_client.post(f"/api/invoices/{invoice_id}/payment-link")

    assert first.status_code == 200, first.text
    url = first.json()["payment_link_url"]
    assert url.startswith("https://inv.example/pay/")
    assert second.json()["payment_link_url"] == url
    # The same key is only ever sent with the same parameters; Stripe rejects
    # a reused key whose body differs.
    assert stripe_requests[0].content == stripe_requests[1].content
    assert stripe_requests[0].headers["Idempotency-Key"].startswith(f"im-invoice-{invoice_id}-")
    form = parse_qs(stripe_requests[0].content.decode())
    assert form["success_url"] == [f"{url}?result=paid"]
    assert form["cancel_url"] == [f"{url}?result=cancelled"]
    assert form["line_items[0][price_data][unit_amount]"] == ["10000"]


@pytest.mark.asyncio
async def test_pay_page_redirects_to_a_fresh_checkout_without_login(test_client, stripe_requests):
    invoice_id = await _payable_invoice(test_client)
    url = (await test_client.post(f"/api/invoices/{invoice_id}/payment-link")).json()[
        "payment_link_url"
    ]
    path = url.removeprefix("https://inv.example")

    async with _public_client() as client:
        response = await client.get(path)
        assert response.status_code == 303
        assert response.headers["location"] == CHECKOUT_URL

        cancelled = await client.get(f"{path}?result=cancelled")
        assert cancelled.status_code == 200
        assert "$100.00 is still due" in cancelled.text
        assert f'href="{path}"' in cancelled.text

        assert (await client.get("/pay/not-a-token")).status_code == 404

    await test_client.post(f"/api/invoices/{invoice_id}/payments", json={"amount": "100.00"})
    async with _public_client() as client:
        paid = await client.get(path)
    assert paid.status_code == 200
    assert "paid in full" in paid.text


@pytest.mark.asyncio
async def test_idempotency_key_rolls_over_every_hour(test_client, stripe_requests, monkeypatch):
    invoice_id = await _payable_invoice(test_client)
    monkeypatch.setattr(stripe_links.time, "time", lambda: 7200.0)
    await test_client.post(f"/api/invoices/{invoice_id}/payment-link")
    await test_client.post(f"/api/invoices/{invoice_id}/payment-link")
    monkeypatch.setattr(stripe_links.time, "time", lambda: 10800.0)
    await test_client.post(f"/api/invoices/{invoice_id}/payment-link")

    keys = [r.headers["Idempotency-Key"] for r in stripe_requests]
    assert keys[0] == keys[1] != keys[2]


@pytest.mark.asyncio
async def test_partial_payment_changes_the_checkout_amount(test_client, stripe_requests):
    invoice_id = await _payable_invoice(test_client)
    url = (await test_client.post(f"/api/invoices/{invoice_id}/payment-link")).json()[
        "payment_link_url"
    ]
    await test_client.post(f"/api/invoices/{invoice_id}/payments", json={"amount": "40.00"})

    async with _public_client() as client:
        await client.get(url.removeprefix("https://inv.example"))

    form = parse_qs(stripe_requests[-1].content.decode())
    assert form["line_items[0][price_data][unit_amount]"] == ["6000"]
    assert (
        stripe_requests[-1].headers["Idempotency-Key"]
        != stripe_requests[0].headers["Idempotency-Key"]
    )


@pytest.mark.asyncio
async def test_link_refused_for_cancelled_invoices_and_without_a_base_url(
    test_client, stripe_requests, monkeypatch
):
    from invoice_machine.config import get_settings

    monkeypatch.setattr(get_settings(), "app_base_url", "")
    invoice_id = await _payable_invoice(test_client, base_url="")
    no_base = await test_client.post(f"/api/invoices/{invoice_id}/payment-link")
    assert no_base.status_code == 400
    assert "base URL" in no_base.json()["detail"]

    await test_client.put("/api/profile", json={"app_base_url": "https://inv.example"})
    await test_client.put(f"/api/invoices/{invoice_id}", json={"status": "cancelled"})
    cancelled = await test_client.post(f"/api/invoices/{invoice_id}/payment-link")
    assert cancelled.status_code == 400
    assert stripe_requests == []
