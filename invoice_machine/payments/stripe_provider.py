"""Stripe-hosted Checkout adapter, imported only when configured."""

from __future__ import annotations

from datetime import UTC, datetime

from starlette.concurrency import run_in_threadpool

from invoice_machine.payments.base import (
    CheckoutRequest,
    CheckoutResult,
    PaymentProviderError,
    ProviderEvent,
    RefundRequest,
    RefundResult,
)


def _stripe_module():
    try:
        import stripe
    except ImportError as exc:  # pragma: no cover - depends on installation extra
        raise PaymentProviderError(
            "Stripe support is not installed. Install Invoice Machine with the 'stripe' extra."
        ) from exc
    return stripe


class StripeProvider:
    name = "stripe"

    def __init__(self, secret_key: str | None, webhook_secret: str | None = None):
        self.secret_key = secret_key
        self.webhook_secret = webhook_secret

    def _require_secret_key(self) -> str:
        if not self.secret_key:
            raise PaymentProviderError("Stripe secret key is not configured")
        return self.secret_key

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutResult:
        stripe = _stripe_module()
        secret_key = self._require_secret_key()

        def _create():
            return stripe.checkout.Session.create(
                api_key=secret_key,
                mode="payment",
                line_items=[
                    {
                        "price_data": {
                            "currency": request.currency_code.lower(),
                            "unit_amount": request.amount_minor,
                            "product_data": {
                                "name": f"Invoice {request.invoice_number}",
                            },
                        },
                        "quantity": 1,
                    }
                ],
                customer_email=request.customer_email or None,
                success_url=request.success_url,
                cancel_url=request.cancel_url,
                metadata=request.metadata,
                payment_intent_data={"metadata": request.metadata},
                idempotency_key=request.idempotency_key,
            )

        try:
            session = await run_in_threadpool(_create)
        except Exception as exc:
            raise PaymentProviderError(f"Stripe Checkout could not be created: {exc}") from exc
        if not session.get("url"):
            raise PaymentProviderError("Stripe did not return a Checkout URL")
        expires_at = session.get("expires_at")
        return CheckoutResult(
            id=session["id"],
            url=session["url"],
            expires_at=(
                datetime.fromtimestamp(int(expires_at), tz=UTC)
                if expires_at is not None
                else None
            ),
        )

    async def expire_checkout(self, checkout_id: str) -> None:
        stripe = _stripe_module()
        secret_key = self._require_secret_key()

        def _expire():
            session = stripe.checkout.Session.retrieve(checkout_id, api_key=secret_key)
            if session.get("status") == "open":
                stripe.checkout.Session.expire(checkout_id, api_key=secret_key)

        try:
            await run_in_threadpool(_expire)
        except Exception as exc:
            raise PaymentProviderError(
                f"Stripe Checkout session could not be expired: {exc}"
            ) from exc

    async def verify_event(self, payload: bytes, signature: str) -> ProviderEvent:
        if not self.webhook_secret:
            raise PaymentProviderError("Stripe webhook secret is not configured")
        stripe = _stripe_module()
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret
            )
        except Exception as exc:
            raise PaymentProviderError("Invalid Stripe webhook signature or payload") from exc
        raw = event.to_dict_recursive() if hasattr(event, "to_dict_recursive") else dict(event)
        created = raw.get("created")
        return ProviderEvent(
            id=str(raw["id"]),
            type=str(raw["type"]),
            data=dict(raw.get("data", {}).get("object", {})),
            occurred_at=(
                datetime.fromtimestamp(int(created), tz=UTC) if created is not None else None
            ),
        )

    async def create_refund(self, request: RefundRequest) -> RefundResult:
        stripe = _stripe_module()
        secret_key = self._require_secret_key()

        def _create():
            return stripe.Refund.create(
                api_key=secret_key,
                payment_intent=request.provider_payment_id,
                amount=request.amount_minor,
                idempotency_key=request.idempotency_key,
            )

        try:
            refund = await run_in_threadpool(_create)
        except Exception as exc:
            raise PaymentProviderError(f"Stripe refund could not be created: {exc}") from exc
        return RefundResult(id=str(refund["id"]), status=str(refund.get("status", "pending")))

    async def test_connection(self) -> dict:
        stripe = _stripe_module()
        secret_key = self._require_secret_key()

        def _retrieve():
            return stripe.Account.retrieve(api_key=secret_key)

        try:
            account = await run_in_threadpool(_retrieve)
        except Exception as exc:
            raise PaymentProviderError(f"Stripe connection failed: {exc}") from exc
        return {
            "success": True,
            "provider": "stripe",
            "account_id": account.get("id"),
            "charges_enabled": bool(account.get("charges_enabled", False)),
            "test_mode": secret_key.startswith("sk_test_"),
        }
