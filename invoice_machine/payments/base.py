"""Provider contract shared by optional payment integrations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class PaymentProviderError(RuntimeError):
    """A safe, user-facing provider integration error."""


@dataclass(frozen=True)
class CheckoutRequest:
    invoice_id: int
    invoice_number: str
    amount_minor: int
    currency_code: str
    customer_email: str | None
    success_url: str
    cancel_url: str
    metadata: dict[str, str]
    idempotency_key: str


@dataclass(frozen=True)
class CheckoutResult:
    id: str
    url: str
    expires_at: datetime | None = None


@dataclass(frozen=True)
class RefundRequest:
    provider_payment_id: str
    amount_minor: int
    idempotency_key: str


@dataclass(frozen=True)
class RefundResult:
    id: str
    status: str


@dataclass(frozen=True)
class ProviderEvent:
    id: str
    type: str
    data: dict[str, Any]
    occurred_at: datetime | None = None


class PaymentProvider(Protocol):
    name: str

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutResult: ...

    async def expire_checkout(self, checkout_id: str) -> None: ...

    async def verify_event(self, payload: bytes, signature: str) -> ProviderEvent: ...

    async def create_refund(self, request: RefundRequest) -> RefundResult: ...

    async def test_connection(self) -> dict: ...
