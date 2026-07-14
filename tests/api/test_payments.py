"""Payment REST API tests."""

import pytest

from invoice_machine.payments.base import (
    CheckoutResult,
    PaymentProviderError,
    ProviderEvent,
    RefundResult,
)


class FakeStripeProvider:
    name = "stripe"

    def __init__(self, event=None):
        self.event = event
        self.checkout_request = None
        self.checkout_calls = 0
        self.expired_checkout_ids = []
        self.refund_request = None
        self.refund_calls = 0

    async def create_checkout(self, request):
        self.checkout_calls += 1
        self.checkout_request = request
        suffix = "" if self.checkout_calls == 1 else f"-{self.checkout_calls}"
        return CheckoutResult(
            id=f"cs_test{suffix}",
            url=f"https://checkout.stripe.test/session{suffix}",
        )

    async def expire_checkout(self, checkout_id):
        self.expired_checkout_ids.append(checkout_id)

    async def verify_event(self, payload, signature):
        if signature != "valid":
            raise PaymentProviderError("Invalid Stripe webhook signature or payload")
        return self.event

    async def create_refund(self, request):
        self.refund_calls += 1
        self.refund_request = request
        return RefundResult(id="re_test", status="pending")

    async def test_connection(self):
        return {"success": True, "provider": "stripe", "test_mode": True}


@pytest.mark.asyncio
async def test_manual_payment_api_updates_invoice(test_client):
    created = await test_client.post(
        "/api/invoices",
        json={"items": [{"description": "Work", "quantity": 1, "unit_price": "1.00"}]},
    )
    invoice_id = created.json()["id"]
    await test_client.put(f"/api/invoices/{invoice_id}", json={"status": "sent"})

    response = await test_client.post(
        f"/api/payments/invoices/{invoice_id}/manual",
        json={"amount": "1.00", "notes": "Cash"},
    )
    assert response.status_code == 201
    assert response.json()["provider"] == "manual"

    detail = await test_client.get(f"/api/invoices/{invoice_id}")
    assert detail.json()["amount_paid"] == "1.00"
    assert detail.json()["amount_outstanding"] == "0.00"
    assert detail.json()["status"] == "paid"


@pytest.mark.asyncio
async def test_manual_refund_api_reuses_idempotency_key(test_client):
    created = await test_client.post(
        "/api/invoices",
        json={"items": [{"description": "Work", "quantity": 1, "unit_price": "1.00"}]},
    )
    invoice_id = created.json()["id"]
    await test_client.put(f"/api/invoices/{invoice_id}", json={"status": "sent"})
    payment = await test_client.post(
        f"/api/payments/invoices/{invoice_id}/manual", json={"amount": "1.00"}
    )
    request = {
        "json": {"amount": "0.40"},
        "headers": {"Idempotency-Key": "manual-refund-api-1"},
    }

    first = await test_client.post(
        f"/api/payments/{payment.json()['id']}/refund", **request
    )
    replay = await test_client.post(
        f"/api/payments/{payment.json()['id']}/refund", **request
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    ledger = await test_client.get(f"/api/payments/invoices/{invoice_id}")
    assert ledger.json()["summary"]["refunded"] == "0.40"
    assert ledger.json()["summary"]["outstanding"] == "0.40"


@pytest.mark.asyncio
async def test_payment_provider_is_disabled_by_default(test_client):
    response = await test_client.get("/api/payments/settings")
    assert response.status_code == 200
    assert response.json() == {
        "online_payments_enabled": False,
        "payment_provider": None,
        "stripe_secret_key_set": False,
        "stripe_webhook_secret_set": False,
    }


async def _configured_invoice(test_client):
    await test_client.put(
        "/api/payments/settings",
        json={
            "payment_provider": "stripe",
            "stripe_secret_key": "sk_test_example",
            "stripe_webhook_secret": "whsec_example",
            "online_payments_enabled": True,
        },
    )
    created = await test_client.post(
        "/api/invoices",
        json={"items": [{"description": "Work", "quantity": 1, "unit_price": "1.00"}]},
    )
    invoice_id = created.json()["id"]
    await test_client.put(f"/api/invoices/{invoice_id}", json={"status": "sent"})
    enabled = await test_client.put(
        f"/api/payments/invoices/{invoice_id}/online", json={"enabled": True}
    )
    return invoice_id, enabled.json()["payment_url"]


@pytest.mark.asyncio
async def test_public_payment_link_creates_hosted_checkout(test_client, monkeypatch):
    provider = FakeStripeProvider()
    monkeypatch.setattr("invoice_machine.api.payments.get_payment_provider", lambda profile: provider)
    invoice_id, payment_url = await _configured_invoice(test_client)

    token = payment_url.rsplit("/", 1)[-1]
    response = await test_client.get(f"/pay/{token}")
    assert response.status_code == 303
    assert response.headers["location"] == "https://checkout.stripe.test/session"
    assert provider.checkout_request.invoice_id == invoice_id
    assert provider.checkout_request.amount_minor == 100
    assert provider.checkout_request.currency_code == "USD"
    assert provider.checkout_request.idempotency_key


@pytest.mark.asyncio
async def test_public_payment_link_reuses_active_checkout(test_client, monkeypatch):
    provider = FakeStripeProvider()
    monkeypatch.setattr("invoice_machine.api.payments.get_payment_provider", lambda profile: provider)
    _invoice_id, payment_url = await _configured_invoice(test_client)
    token = payment_url.rsplit("/", 1)[-1]

    first = await test_client.get(f"/pay/{token}")
    first_key = provider.checkout_request.idempotency_key
    second = await test_client.get(f"/pay/{token}")

    assert first.status_code == 303
    assert second.status_code == 303
    assert second.headers["location"] == first.headers["location"]
    assert provider.checkout_calls == 1
    assert provider.checkout_request.idempotency_key == first_key


@pytest.mark.asyncio
async def test_checkout_is_expired_before_balance_change_creates_replacement(
    test_client, monkeypatch
):
    provider = FakeStripeProvider()
    monkeypatch.setattr("invoice_machine.api.payments.get_payment_provider", lambda profile: provider)
    monkeypatch.setattr(
        "invoice_machine.payments.registry.get_provider_for_existing_payment",
        lambda profile, provider_name: provider,
    )
    invoice_id, payment_url = await _configured_invoice(test_client)
    token = payment_url.rsplit("/", 1)[-1]
    await test_client.get(f"/pay/{token}")
    await test_client.post(
        f"/api/invoices/{invoice_id}/items",
        params={"description": "More work", "quantity": 1, "unit_price": 1},
    )
    assert provider.expired_checkout_ids == ["cs_test"]

    replacement = await test_client.get(f"/pay/{token}")

    assert replacement.status_code == 303
    assert replacement.headers["location"].endswith("session-2")
    assert provider.checkout_calls == 2


@pytest.mark.asyncio
async def test_rotating_payment_token_expires_active_checkout(test_client, monkeypatch):
    provider = FakeStripeProvider()
    monkeypatch.setattr("invoice_machine.api.payments.get_payment_provider", lambda profile: provider)
    monkeypatch.setattr(
        "invoice_machine.payments.registry.get_provider_for_existing_payment",
        lambda profile, provider_name: provider,
    )
    invoice_id, payment_url = await _configured_invoice(test_client)
    token = payment_url.rsplit("/", 1)[-1]
    await test_client.get(f"/pay/{token}")

    rotated = await test_client.put(
        f"/api/payments/invoices/{invoice_id}/online",
        json={"enabled": True, "rotate_token": True},
    )

    assert rotated.status_code == 200
    assert rotated.json()["payment_url"] != payment_url
    assert provider.expired_checkout_ids == ["cs_test"]


@pytest.mark.asyncio
async def test_verified_webhook_marks_invoice_paid_once(test_client, monkeypatch):
    invoice_id, _payment_url = await _configured_invoice(test_client)
    event = ProviderEvent(
        id="evt_api_1",
        type="checkout.session.completed",
        data={
            "id": "cs_api_1",
            "payment_intent": "pi_api_1",
            "payment_status": "paid",
            "amount_total": 100,
            "currency": "usd",
            "metadata": {
                "invoice_id": str(invoice_id),
                "expected_amount_minor": "100",
                "currency_code": "USD",
            },
        },
    )
    provider = FakeStripeProvider(event)
    monkeypatch.setattr(
        "invoice_machine.api.payments.get_stripe_webhook_provider", lambda profile: provider
    )

    first = await test_client.post(
        "/api/payments/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "valid"}
    )
    replay = await test_client.post(
        "/api/payments/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "valid"}
    )
    assert first.status_code == 200
    assert replay.json()["duplicate"] is True

    invoice = await test_client.get(f"/api/invoices/{invoice_id}")
    assert invoice.json()["status"] == "paid"
    assert invoice.json()["amount_paid"] == "1.00"


@pytest.mark.asyncio
async def test_webhook_reconciles_checkout_after_online_payments_disabled(
    test_client, monkeypatch
):
    invoice_id, _payment_url = await _configured_invoice(test_client)
    await test_client.put(
        "/api/payments/settings", json={"online_payments_enabled": False}
    )
    event = ProviderEvent(
        id="evt_after_disable",
        type="checkout.session.completed",
        data={
            "id": "cs_after_disable",
            "payment_intent": "pi_after_disable",
            "payment_status": "paid",
            "amount_total": 100,
            "currency": "usd",
            "metadata": {
                "invoice_id": str(invoice_id),
                "expected_amount_minor": "100",
                "currency_code": "USD",
            },
        },
    )
    provider = FakeStripeProvider(event)
    monkeypatch.setattr(
        "invoice_machine.api.payments.get_stripe_webhook_provider", lambda profile: provider
    )

    response = await test_client.post(
        "/api/payments/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid"},
    )

    assert response.status_code == 200
    invoice = await test_client.get(f"/api/invoices/{invoice_id}")
    assert invoice.json()["status"] == "paid"


@pytest.mark.asyncio
async def test_api_does_not_accept_partially_paid_without_a_ledger_payment(test_client):
    created = await test_client.post(
        "/api/invoices",
        json={"items": [{"description": "Work", "quantity": 1, "unit_price": 1}]},
    )
    response = await test_client.put(
        f"/api/invoices/{created.json()['id']}", json={"status": "partially_paid"}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_forged_webhook_is_rejected(test_client, monkeypatch):
    await _configured_invoice(test_client)
    provider = FakeStripeProvider()
    monkeypatch.setattr(
        "invoice_machine.api.payments.get_stripe_webhook_provider", lambda profile: provider
    )
    response = await test_client.post(
        "/api/payments/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "forged"}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_provider_refund_is_initiated_and_waits_for_webhook(test_client, monkeypatch):
    invoice_id, _payment_url = await _configured_invoice(test_client)
    event = ProviderEvent(
        id="evt_refundable",
        type="checkout.session.completed",
        data={
            "id": "cs_refundable",
            "payment_intent": "pi_refundable",
            "payment_status": "paid",
            "amount_total": 100,
            "currency": "usd",
            "metadata": {
                "invoice_id": str(invoice_id),
                "expected_amount_minor": "100",
                "currency_code": "USD",
            },
        },
    )
    provider = FakeStripeProvider(event)
    monkeypatch.setattr(
        "invoice_machine.api.payments.get_stripe_webhook_provider", lambda profile: provider
    )
    monkeypatch.setattr(
        "invoice_machine.api.payments.get_provider_for_existing_payment",
        lambda profile, provider_name: provider,
    )
    await test_client.post(
        "/api/payments/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid"},
    )
    ledger = await test_client.get(f"/api/payments/invoices/{invoice_id}")
    payment_id = ledger.json()["payments"][0]["id"]

    refund = await test_client.post(
        f"/api/payments/{payment_id}/refund",
        json={"amount": "0.40"},
        headers={"Idempotency-Key": "refund-api-test-1"},
    )
    assert refund.status_code == 200
    assert refund.json()["refund_initiated"] is True
    assert provider.refund_request.provider_payment_id == "pi_refundable"
    assert provider.refund_request.amount_minor == 40
    assert provider.refund_request.idempotency_key == "refund-api-test-1"

    replay = await test_client.post(
        f"/api/payments/{payment_id}/refund",
        json={"amount": "0.40"},
        headers={"Idempotency-Key": "refund-api-test-1"},
    )
    assert replay.status_code == 200
    assert replay.json()["provider_refund_id"] == "re_test"
    assert provider.refund_calls == 1

    unchanged = await test_client.get(f"/api/payments/invoices/{invoice_id}")
    assert unchanged.json()["summary"]["outstanding"] == "0.00"

    provider.event = ProviderEvent(
        id="evt_refund_applied",
        type="charge.refunded",
        data={"payment_intent": "pi_refundable", "amount_refunded": 40},
    )
    applied = await test_client.post(
        "/api/payments/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "valid"},
    )
    assert applied.status_code == 200

    replay_after_webhook = await test_client.post(
        f"/api/payments/{payment_id}/refund",
        json={"amount": "0.40"},
        headers={"Idempotency-Key": "refund-api-test-1"},
    )
    assert replay_after_webhook.status_code == 200
    assert replay_after_webhook.json()["provider_refund_id"] == "re_test"
    assert provider.refund_calls == 1

    updated = await test_client.get(f"/api/payments/invoices/{invoice_id}")
    assert updated.json()["summary"]["outstanding"] == "0.40"
