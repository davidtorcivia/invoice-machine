"""Optional payment-provider adapters."""

from invoice_machine.payments.registry import (
    get_payment_provider,
    get_provider_for_existing_payment,
    get_stripe_webhook_provider,
)

__all__ = [
    "get_payment_provider",
    "get_provider_for_existing_payment",
    "get_stripe_webhook_provider",
]
