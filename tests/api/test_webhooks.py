"""Tests for the Stripe webhook endpoint."""

import hashlib
import hmac
import json
import time
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio

WEBHOOK_SECRET = "whsec_test_secret"


def sign(body: bytes, *, timestamp: int | None = None, secret: str = WEBHOOK_SECRET) -> dict:
    """Build the Stripe-Signature header for a raw body, as Stripe would."""
    timestamp = timestamp if timestamp is not None else int(time.time())
    signature = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return {"Stripe-Signature": f"t={timestamp},v1={signature}"}


def checkout_event(invoice_id: int, *, event_id: str, currency: str = "usd", amount: int = 10000):
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_1",
                "payment_status": "paid",
                "currency": currency,
                "amount_total": amount,
                "metadata": {"invoice_id": str(invoice_id)},
            }
        },
    }


@pytest_asyncio.fixture
async def paid_invoice_id(test_client):
    """Enable payments with a known signing secret and return an unpaid invoice id."""
    import invoice_machine.database as db
    from invoice_machine.crypto import encrypt_credential
    from invoice_machine.database import BusinessProfile, Client, Invoice

    async with db.async_session_maker() as session:
        profile = await BusinessProfile.get(session)
        profile.payments_enabled = 1
        profile.stripe_webhook_secret = encrypt_credential(WEBHOOK_SECRET)

        client = Client(name="Webhook Co", email="pay@example.com")
        session.add(client)
        await session.commit()

        invoice = Invoice(
            invoice_number="WH-1",
            client_id=client.id,
            client_name=client.name,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            currency_code="USD",
            status="sent",
        )
        session.add(invoice)
        await session.commit()
        return invoice.id


async def post_event(client, event, **header_kwargs):
    body = json.dumps(event).encode()
    return await client.post(
        "/api/webhooks/stripe", content=body, headers=sign(body, **header_kwargs)
    )


@pytest.mark.asyncio
async def test_valid_event_records_a_payment(test_client, paid_invoice_id):
    import invoice_machine.database as db
    from invoice_machine.services import PaymentService

    response = await post_event(test_client, checkout_event(paid_invoice_id, event_id="evt_1"))

    assert response.status_code == 200
    assert response.json()["handled"] is True
    async with db.async_session_maker() as session:
        payment = await PaymentService.find_by_external_id(session, "stripe", "evt_1")
        assert payment is not None
        assert payment.amount == Decimal("100.00")


@pytest.mark.asyncio
async def test_replayed_event_id_is_a_duplicate_no_op(test_client, paid_invoice_id):
    import invoice_machine.database as db
    from invoice_machine.services import PaymentService

    event = checkout_event(paid_invoice_id, event_id="evt_dup")
    await post_event(test_client, event)
    response = await post_event(test_client, event)

    assert response.json() == {"received": True, "handled": True, "duplicate": True}
    async with db.async_session_maker() as session:
        payments = await PaymentService.list_payments(session, invoice_id=paid_invoice_id)
        assert len(payments) == 1


@pytest.mark.asyncio
async def test_bad_signature_is_rejected(test_client, paid_invoice_id):
    body = json.dumps(checkout_event(paid_invoice_id, event_id="evt_bad")).encode()
    headers = sign(body, secret="whsec_wrong_secret")

    response = await test_client.post("/api/webhooks/stripe", content=body, headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid signature"


@pytest.mark.asyncio
async def test_stale_timestamp_is_rejected(test_client, paid_invoice_id):
    response = await post_event(
        test_client,
        checkout_event(paid_invoice_id, event_id="evt_stale"),
        timestamp=int(time.time()) - 1000,
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_currency_mismatch_is_not_recorded(test_client, paid_invoice_id):
    response = await post_event(
        test_client, checkout_event(paid_invoice_id, event_id="evt_eur", currency="eur")
    )

    assert response.json()["reason"] == "currency mismatch"


@pytest.mark.asyncio
async def test_non_actionable_event_is_acknowledged_and_ignored(test_client, paid_invoice_id):
    response = await post_event(
        test_client, {"id": "evt_other", "type": "customer.created", "data": {"object": {}}}
    )

    assert response.json() == {"received": True, "handled": False, "reason": "event not actionable"}


@pytest.mark.asyncio
async def test_unknown_invoice_is_acknowledged_and_logged(test_client, paid_invoice_id):
    response = await post_event(test_client, checkout_event(999999, event_id="evt_missing"))

    assert response.json()["reason"] == "invoice not found"


@pytest.mark.asyncio
async def test_oversized_body_is_refused_before_verification(test_client, paid_invoice_id):
    body = b"x" * (512 * 1024 + 1)

    response = await test_client.post("/api/webhooks/stripe", content=body, headers=sign(body))

    assert response.status_code == 413


@pytest.mark.asyncio
async def test_webhook_is_404_when_payments_are_disabled(test_client):
    response = await post_event(test_client, {"id": "evt_off", "type": "customer.created"})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_missing_signing_secret_is_503(test_client):
    import invoice_machine.database as db
    from invoice_machine.database import BusinessProfile

    async with db.async_session_maker() as session:
        profile = await BusinessProfile.get(session)
        profile.payments_enabled = 1
        profile.stripe_webhook_secret = None
        await session.commit()

    response = await post_event(test_client, {"id": "evt_nosecret", "type": "customer.created"})

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_unrecordable_payment_is_acknowledged_not_retried(
    test_client, paid_invoice_id, monkeypatch
):
    async def refuse(*args, **kwargs):
        raise ValueError("payment refused")

    monkeypatch.setattr("invoice_machine.services.PaymentService.record_payment", refuse)

    response = await post_event(
        test_client, checkout_event(paid_invoice_id, event_id="evt_bad_amt")
    )

    assert response.status_code == 200
    assert response.json()["reason"] == "could not record payment"
