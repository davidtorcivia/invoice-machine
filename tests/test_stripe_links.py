"""Tests for the Stripe payment-link integration and webhook verification."""

import hashlib
import hmac
import json
import time
from decimal import Decimal

import pytest

from invoice_machine.service.stripe_links import (
    extract_payment_from_event,
    from_stripe_amount,
    to_stripe_amount,
    verify_webhook_signature,
)


def _sign(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Build a valid Stripe-Signature header for a payload."""
    ts = timestamp if timestamp is not None else int(time.time())
    signature = hmac.new(
        secret.encode(), f"{ts}".encode() + b"." + payload, hashlib.sha256
    ).hexdigest()
    return f"t={ts},v1={signature}"


SECRET = "whsec_test_secret_value"


class TestAmountConversion:
    """Stripe uses integer minor units, except for zero-decimal currencies."""

    def test_usd_uses_cents(self):
        assert to_stripe_amount(Decimal("12.34"), "USD") == 1234
        assert from_stripe_amount(1234, "USD") == Decimal("12.34")

    def test_jpy_has_no_minor_unit(self):
        """Multiplying JPY by 100 would overcharge the customer 100x."""
        assert to_stripe_amount(Decimal("1200"), "JPY") == 1200
        assert from_stripe_amount(1200, "JPY") == Decimal("1200")

    def test_round_trip_preserves_value(self):
        for amount in ("0.01", "99.99", "1000.00"):
            value = Decimal(amount)
            assert from_stripe_amount(to_stripe_amount(value, "USD"), "USD") == value


class TestWebhookSignatureVerification:
    """Nothing in the payload is trusted until the signature verifies."""

    def test_valid_signature_returns_the_event(self):
        payload = json.dumps({"id": "evt_1", "type": "ping"}).encode()
        event = verify_webhook_signature(payload, _sign(payload, SECRET), SECRET)
        assert event["id"] == "evt_1"

    def test_wrong_secret_is_rejected(self):
        payload = json.dumps({"id": "evt_1"}).encode()
        header = _sign(payload, "whsec_a_different_secret")
        with pytest.raises(ValueError, match="signature verification failed"):
            verify_webhook_signature(payload, header, SECRET)

    def test_tampered_payload_is_rejected(self):
        payload = json.dumps({"id": "evt_1", "amount": 100}).encode()
        header = _sign(payload, SECRET)
        tampered = json.dumps({"id": "evt_1", "amount": 100000}).encode()

        with pytest.raises(ValueError, match="signature verification failed"):
            verify_webhook_signature(tampered, header, SECRET)

    def test_replayed_old_event_is_rejected(self):
        """An old-but-validly-signed request must not be replayable forever."""
        payload = json.dumps({"id": "evt_1"}).encode()
        stale = _sign(payload, SECRET, timestamp=int(time.time()) - 3600)

        with pytest.raises(ValueError, match="tolerance window"):
            verify_webhook_signature(payload, stale, SECRET)

    def test_missing_header_is_rejected(self):
        with pytest.raises(ValueError, match="Missing Stripe-Signature"):
            verify_webhook_signature(b"{}", None, SECRET)

    def test_malformed_header_is_rejected(self):
        for header in ("garbage", "t=123", "v1=abc", ""):
            with pytest.raises(ValueError):
                verify_webhook_signature(b"{}", header, SECRET)

    def test_missing_signing_secret_is_rejected(self):
        payload = b"{}"
        with pytest.raises(ValueError, match="signing secret"):
            verify_webhook_signature(payload, _sign(payload, SECRET), "")

    def test_multiple_v1_signatures_are_accepted(self):
        """Stripe sends several v1 values during a secret rotation."""
        payload = json.dumps({"id": "evt_1"}).encode()
        ts = int(time.time())
        good = hmac.new(
            SECRET.encode(), f"{ts}".encode() + b"." + payload, hashlib.sha256
        ).hexdigest()
        header = f"t={ts},v1=0000000000,v1={good}"

        assert verify_webhook_signature(payload, header, SECRET)["id"] == "evt_1"

    def test_non_json_payload_is_rejected(self):
        payload = b"not json"
        with pytest.raises(ValueError, match="not valid JSON"):
            verify_webhook_signature(payload, _sign(payload, SECRET), SECRET)


class TestEventExtraction:
    """Only genuinely-paid sessions become payments."""

    def _session_event(self, **overrides):
        session = {
            "id": "cs_test_1",
            "payment_status": "paid",
            "currency": "usd",
            "amount_total": 25000,
            "metadata": {"invoice_id": "42"},
        }
        session.update(overrides)
        return {
            "id": "evt_abc",
            "type": "checkout.session.completed",
            "data": {"object": session},
        }

    def test_completed_paid_session_maps_to_a_payment(self):
        details = extract_payment_from_event(self._session_event())
        assert details["invoice_id"] == 42
        assert details["amount"] == Decimal("250.00")
        assert details["external_id"] == "evt_abc"

    def test_unpaid_session_is_ignored(self):
        """A completed session that is still awaiting funds is not money received."""
        assert extract_payment_from_event(self._session_event(payment_status="unpaid")) is None

    def test_unrelated_event_types_are_ignored(self):
        event = self._session_event()
        event["type"] = "customer.created"
        assert extract_payment_from_event(event) is None

    def test_missing_invoice_metadata_is_ignored(self):
        event = self._session_event(metadata={})
        event["data"]["object"].pop("client_reference_id", None)
        assert extract_payment_from_event(event) is None

    def test_client_reference_id_is_used_as_a_fallback(self):
        event = self._session_event(metadata={}, client_reference_id="7")
        assert extract_payment_from_event(event)["invoice_id"] == 7

    def test_zero_decimal_currency_is_not_divided(self):
        details = extract_payment_from_event(
            self._session_event(currency="jpy", amount_total=5000)
        )
        assert details["amount"] == Decimal("5000")
