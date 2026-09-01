"""Stripe hosted payment links for invoices.

Implemented against Stripe's REST API directly rather than the SDK: this app has
a deliberately small dependency set, and the surface used here is two calls plus
webhook signature verification.

Design notes:
- A Checkout Session (not the deprecated Charges API) is created per invoice for
  the *outstanding* balance, so a partially-paid invoice links for what's left.
- ``payment_method_types`` is never sent, which leaves Stripe's dynamic payment
  methods enabled — the methods shown are controlled from the Stripe Dashboard.
- The API key is stored encrypted and never logged or returned to the client.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from decimal import Decimal

import httpx

from invoice_machine.database import BusinessProfile, Invoice
from invoice_machine.utils import utc_now

logger = logging.getLogger(__name__)

STRIPE_API_BASE = "https://api.stripe.com/v1"
# Pinned so a Stripe-side default bump can't silently change response shapes.
STRIPE_API_VERSION = "2026-06-24.dahlia"

_HTTP_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# Tolerance for webhook timestamp skew, per Stripe's replay-protection guidance.
WEBHOOK_TOLERANCE_SECONDS = 300

# Currencies with no minor unit: the amount is passed as-is, not multiplied.
_ZERO_DECIMAL_CURRENCIES = {
    "BIF",
    "CLP",
    "DJF",
    "GNF",
    "JPY",
    "KMF",
    "KRW",
    "MGA",
    "PYG",
    "RWF",
    "UGX",
    "VND",
    "VUV",
    "XAF",
    "XOF",
    "XPF",
}
# Currencies with 1000 minor units to the major unit. Treating these as 2-decimal
# undercharges the customer by a factor of ten.
_THREE_DECIMAL_CURRENCIES = {"BHD", "JOD", "KWD", "OMR", "TND"}


class StripeError(Exception):
    """Raised when Stripe rejects a request or is unreachable."""


def currency_exponent(currency_code: str) -> int:
    """Number of decimal places in the currency's minor unit."""
    code = (currency_code or "USD").upper()
    if code in _ZERO_DECIMAL_CURRENCIES:
        return 0
    if code in _THREE_DECIMAL_CURRENCIES:
        return 3
    return 2


def to_stripe_amount(amount: Decimal, currency_code: str) -> int:
    """Convert a decimal amount to Stripe's integer minor units.

    Refuses to charge an amount the currency cannot express rather than
    truncating it, so a rounding mistake surfaces as an error instead of a
    silently wrong charge.
    """
    value = Decimal(str(amount))
    if not value.is_finite() or value < 0:
        raise ValueError("Amount must be finite and non-negative")

    exponent = currency_exponent(currency_code)
    scaled = value * (Decimal(10) ** exponent)
    if scaled != scaled.to_integral_value():
        raise ValueError(
            f"{(currency_code or 'USD').upper()} supports at most "
            f"{exponent} decimal place{'s' if exponent != 1 else ''}"
        )
    return int(scaled)


def from_stripe_amount(amount: int, currency_code: str) -> Decimal:
    """Convert Stripe's integer minor units back to a decimal amount."""
    exponent = currency_exponent(currency_code)
    return Decimal(amount) / (Decimal(10) ** exponent)


def get_stripe_secret_key(profile: BusinessProfile) -> str | None:
    """Decrypt the stored Stripe API key, or None when unusable."""
    from invoice_machine.crypto import UnencryptedCredentialError, decrypt_credential

    if not profile.stripe_secret_key:
        return None
    try:
        return decrypt_credential(profile.stripe_secret_key)
    except (ValueError, UnencryptedCredentialError) as exc:
        # Never include the credential itself in the log line.
        logger.error("Stored Stripe API key could not be decrypted: %s", exc)
        return None


def get_stripe_webhook_secret(profile: BusinessProfile) -> str | None:
    """Decrypt the stored Stripe webhook signing secret, or None when unusable."""
    from invoice_machine.crypto import UnencryptedCredentialError, decrypt_credential

    if not profile.stripe_webhook_secret:
        return None
    try:
        return decrypt_credential(profile.stripe_webhook_secret)
    except (ValueError, UnencryptedCredentialError) as exc:
        logger.error("Stored Stripe webhook secret could not be decrypted: %s", exc)
        return None


def _api_headers(secret_key: str, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Stripe-Version": STRIPE_API_VERSION,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _raise_for_stripe_error(response: httpx.Response) -> None:
    """Turn a Stripe error response into a StripeError with a safe message."""
    if response.is_success:
        return
    message = "Stripe request failed"
    try:
        payload = response.json()
        message = payload.get("error", {}).get("message") or message
    except ValueError:
        pass
    # Log status only — the response body can echo request params.
    logger.error("Stripe API error (HTTP %s)", response.status_code)
    raise StripeError(message)


async def create_payment_link(
    profile: BusinessProfile,
    invoice: Invoice,
    success_url: str,
    cancel_url: str,
) -> dict:
    """Create a Stripe Checkout Session for an invoice's outstanding balance.

    Returns ``{"id", "url"}``. Raises StripeError on any failure.
    """
    secret_key = get_stripe_secret_key(profile)
    if not secret_key:
        raise StripeError("Stripe is not configured. Add an API key in settings.")

    amount_due = invoice.amount_due
    if amount_due <= 0:
        raise StripeError("Invoice has no outstanding balance to collect.")

    currency = (invoice.currency_code or "USD").lower()
    doc_label = "Quote" if invoice.document_type == "quote" else "Invoice"
    product_name = f"{doc_label} {invoice.invoice_number}"

    # Form-encoded, per Stripe's API. Note there is deliberately no
    # payment_method_types field: omitting it keeps dynamic payment methods on,
    # so the accepted methods are managed from the Stripe Dashboard.
    form: dict[str, str] = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(invoice.id),
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": currency,
        "line_items[0][price_data][unit_amount]": str(
            to_stripe_amount(amount_due, invoice.currency_code)
        ),
        "line_items[0][price_data][product_data][name]": product_name,
        # Echoed back on the webhook so the payment can be matched to the invoice
        # without trusting client-controlled fields.
        "metadata[invoice_id]": str(invoice.id),
        "metadata[invoice_number]": invoice.invoice_number,
        "payment_intent_data[metadata][invoice_id]": str(invoice.id),
        "integration_identifier": f"invoice-machine-{secrets.token_hex(4)}",
    }
    if invoice.client_email:
        form["customer_email"] = invoice.client_email

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(
                f"{STRIPE_API_BASE}/checkout/sessions",
                data=form,
                headers=_api_headers(
                    secret_key,
                    # Re-creating a link for the same invoice+amount reuses the
                    # session instead of littering the Stripe account.
                    idempotency_key=f"im-invoice-{invoice.id}-{amount_due}",
                ),
            )
    except httpx.HTTPError as exc:
        raise StripeError(f"Could not reach Stripe: {exc}") from exc

    _raise_for_stripe_error(response)
    payload = response.json()
    return {"id": payload.get("id"), "url": payload.get("url")}


async def verify_stripe_key(profile: BusinessProfile) -> dict:
    """Check the stored API key by making a trivial authenticated request."""
    secret_key = get_stripe_secret_key(profile)
    if not secret_key:
        return {"success": False, "error": "No Stripe API key is configured."}

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.get(
                f"{STRIPE_API_BASE}/checkout/sessions",
                params={"limit": 1},
                headers=_api_headers(secret_key),
            )
    except httpx.HTTPError as exc:
        return {"success": False, "error": f"Could not reach Stripe: {exc}"}

    if not response.is_success:
        try:
            message = response.json().get("error", {}).get("message", "Request rejected")
        except ValueError:
            message = "Request rejected"
        return {"success": False, "error": message}

    return {
        "success": True,
        "message": "Stripe credentials verified.",
        "mode": "live" if secret_key.startswith(("sk_live_", "rk_live_")) else "test",
    }


def verify_webhook_signature(
    payload: bytes,
    signature_header: str | None,
    webhook_secret: str,
    tolerance_seconds: int = WEBHOOK_TOLERANCE_SECONDS,
) -> dict:
    """Verify a Stripe webhook signature and return the parsed event.

    Implements Stripe's scheme: the header carries ``t=<timestamp>`` and one or
    more ``v1=<signature>`` values, where each signature is
    HMAC-SHA256("{t}.{raw_body}") keyed with the endpoint's signing secret.
    Comparison is constant-time and the timestamp is checked against a tolerance
    window so a captured request cannot be replayed indefinitely.

    Raises ValueError if the request is not a genuine, fresh Stripe event.
    """
    if not signature_header:
        raise ValueError("Missing Stripe-Signature header")
    if not webhook_secret:
        raise ValueError("No webhook signing secret is configured")

    timestamp: str | None = None
    signatures: list[str] = []
    for part in signature_header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)

    if not timestamp or not signatures:
        raise ValueError("Malformed Stripe-Signature header")

    try:
        event_time = int(timestamp)
    except ValueError:
        raise ValueError("Malformed Stripe-Signature timestamp") from None

    if abs(time.time() - event_time) > tolerance_seconds:
        raise ValueError("Stripe webhook timestamp outside the tolerance window")

    signed_payload = timestamp.encode() + b"." + payload
    expected = hmac.new(webhook_secret.encode(), signed_payload, hashlib.sha256).hexdigest()

    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise ValueError("Stripe webhook signature verification failed")

    try:
        return json.loads(payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Stripe webhook payload is not valid JSON") from None


def extract_payment_from_event(event: dict) -> dict | None:
    """Pull the invoice id and paid amount out of a completed-payment event.

    Returns None for events this app does not act on. Only the *server-side*
    metadata Stripe echoes back is trusted for the invoice id.
    """
    event_type = event.get("type")
    if event_type not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return None

    session = (event.get("data") or {}).get("object") or {}

    # A completed session with an unpaid status (e.g. an async method still
    # pending) must not be recorded as money received.
    if session.get("payment_status") not in ("paid", "no_payment_required"):
        return None

    metadata = session.get("metadata") or {}
    raw_invoice_id = metadata.get("invoice_id") or session.get("client_reference_id")
    if raw_invoice_id is None:
        return None
    try:
        invoice_id = int(raw_invoice_id)
    except (TypeError, ValueError):
        return None

    currency = (session.get("currency") or "usd").upper()
    amount_total = session.get("amount_total")
    if amount_total is None:
        return None

    return {
        "invoice_id": invoice_id,
        "amount": from_stripe_amount(int(amount_total), currency),
        "currency_code": currency,
        # Stripe guarantees event ids are unique; used for idempotency.
        "external_id": event.get("id"),
        "session_id": session.get("id"),
        "payment_date": utc_now().date(),
    }
