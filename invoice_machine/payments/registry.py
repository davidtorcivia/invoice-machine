"""Payment-provider registry and credential loading."""

from __future__ import annotations

from invoice_machine.crypto import decrypt_credential
from invoice_machine.database import BusinessProfile
from invoice_machine.payments.base import PaymentProvider, PaymentProviderError


def get_payment_provider(profile: BusinessProfile) -> PaymentProvider:
    if not profile.online_payments_enabled:
        raise PaymentProviderError("Online payments are disabled")
    if profile.payment_provider != "stripe":
        raise PaymentProviderError("No supported payment provider is configured")
    if not profile.stripe_secret_key:
        raise PaymentProviderError("Stripe secret key is not configured")

    from invoice_machine.payments.stripe_provider import StripeProvider

    return StripeProvider(
        decrypt_credential(profile.stripe_secret_key),
        decrypt_credential(profile.stripe_webhook_secret)
        if profile.stripe_webhook_secret
        else None,
    )


def get_stripe_webhook_provider(profile: BusinessProfile) -> PaymentProvider:
    """Load Stripe solely for signed event reconciliation.

    Existing Checkout sessions and payments must remain reconcilable after an
    administrator disables new links or changes the active provider.
    """
    if not profile.stripe_webhook_secret:
        raise PaymentProviderError("Stripe webhook secret is not configured")
    from invoice_machine.payments.stripe_provider import StripeProvider

    return StripeProvider(
        decrypt_credential(profile.stripe_secret_key) if profile.stripe_secret_key else None,
        decrypt_credential(profile.stripe_webhook_secret),
    )


def get_provider_for_existing_payment(
    profile: BusinessProfile, provider_name: str
) -> PaymentProvider:
    """Load credentials for an existing transaction without enabling new links."""
    if provider_name != "stripe" or not profile.stripe_secret_key:
        raise PaymentProviderError("The payment's provider credentials are not configured")
    from invoice_machine.payments.stripe_provider import StripeProvider

    return StripeProvider(
        decrypt_credential(profile.stripe_secret_key),
        decrypt_credential(profile.stripe_webhook_secret)
        if profile.stripe_webhook_secret
        else None,
    )
