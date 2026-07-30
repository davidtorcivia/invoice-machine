"""Provider-neutral invoice payment ledger and balance rules."""

from __future__ import annotations

import secrets
from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import (
    BusinessProfile,
    Invoice,
    Payment,
    PaymentAdjustment,
    PaymentEvent,
    PaymentRefund,
)
from invoice_machine.payments.base import PaymentProviderError, ProviderEvent
from invoice_machine.payments.currency import from_minor_units
from invoice_machine.service.common import quantize_money
from invoice_machine.utils import ensure_utc, utc_now

SETTLED_PAYMENT_STATUSES = {"succeeded", "partially_refunded"}
PAYMENT_DRIVEN_INVOICE_STATUSES = {"paid", "partially_paid"}
TERMINAL_PROVIDER_PAYMENT_STATUSES = {
    "succeeded",
    "needs_review",
    "partially_refunded",
    "refunded",
    "disputed",
}


class PaymentService:
    """Maintain payment records and synchronize invoice balance state."""

    @staticmethod
    async def list_payments(session: AsyncSession, invoice_id: int) -> list[Payment]:
        result = await session.execute(
            select(Payment)
            .where(Payment.invoice_id == invoice_id)
            .order_by(Payment.occurred_at.desc(), Payment.id.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def payment_summary(session: AsyncSession, invoice: Invoice) -> dict:
        payments = await PaymentService.list_payments(session, invoice.id)
        return PaymentService.summarize(invoice, payments)

    @staticmethod
    async def _sync_invoice_state(session: AsyncSession, invoice: Invoice) -> dict:
        summary = await PaymentService.payment_summary(session, invoice)
        now = utc_now()

        if summary["total"] > 0 and summary["outstanding"] == 0:
            if invoice.status != "paid":
                invoice.status = "paid"
                invoice.paid_at = now
        elif summary["paid"] > 0:
            invoice.status = "partially_paid"
            invoice.paid_at = None
        elif invoice.status in PAYMENT_DRIVEN_INVOICE_STATUSES:
            invoice.status = (
                "overdue"
                if invoice.due_date and invoice.due_date < now.date()
                else "sent"
            )
            invoice.paid_at = None

        invoice.updated_at = now
        return summary

    @staticmethod
    async def record_manual_payment(
        session: AsyncSession,
        invoice_id: int,
        amount: Decimal | str | int | float,
        *,
        occurred_at: datetime | None = None,
        notes: str | None = None,
        commit: bool = True,
        allow_unissued: bool = False,
        idempotency_key: str | None = None,
    ) -> Payment:
        """Record a manual payment.

        Pass `idempotency_key` to make the call replay-safe: a repeat with the
        same key returns the payment already recorded instead of adding a
        second one. This matters for partial payments specifically - the
        outstanding-balance check below already rejects a repeated *full*
        payment, but recording 40.00 twice against a 100.00 invoice would
        otherwise look like 80.00 received.

        Keys are unique per provider, so two genuinely separate payments of the
        same amount are still fine; they just need different keys.
        """
        if idempotency_key is not None:
            idempotency_key = idempotency_key.strip()
            if not idempotency_key:
                raise ValueError("idempotency_key must not be blank")
            existing = await PaymentService._find_by_idempotency_key(
                session, idempotency_key
            )
            if existing is not None:
                return existing

        invoice = await session.get(Invoice, invoice_id)
        if not invoice or invoice.deleted_at is not None:
            raise ValueError("Invoice not found")
        if invoice.document_type != "invoice":
            raise ValueError("Payments cannot be recorded against quotes")
        if invoice.status in {"draft", "cancelled"} and not allow_unissued:
            raise ValueError(f"Payments cannot be recorded against a {invoice.status} invoice")

        payment_amount = quantize_money(amount)
        if payment_amount <= 0:
            raise ValueError("Payment amount must be greater than zero")
        summary = await PaymentService.payment_summary(session, invoice)
        if payment_amount > summary["outstanding"]:
            raise ValueError(
                f"Payment exceeds outstanding balance of {summary['outstanding']} "
                f"{invoice.currency_code}"
            )

        payment = Payment(
            invoice_id=invoice.id,
            amount=payment_amount,
            refunded_amount=Decimal("0.00"),
            currency_code=invoice.currency_code,
            provider="manual",
            status="succeeded",
            notes=notes,
            occurred_at=ensure_utc(occurred_at) or utc_now(),
            idempotency_key=idempotency_key,
        )
        session.add(payment)
        try:
            await session.flush()
        except IntegrityError:
            # Two concurrent calls raced past the lookup above and both tried to
            # insert the same key; the unique index let exactly one through.
            # Return the winner rather than failing the caller, which is the
            # whole point of supplying a key.
            if idempotency_key is None:
                raise
            await session.rollback()
            existing = await PaymentService._find_by_idempotency_key(
                session, idempotency_key
            )
            if existing is None:
                raise
            return existing

        await PaymentService._sync_invoice_state(session, invoice)
        if commit:
            await session.commit()
            await session.refresh(payment)
        else:
            await session.flush()
        return payment

    @staticmethod
    async def _find_by_idempotency_key(
        session: AsyncSession, idempotency_key: str
    ) -> Payment | None:
        """Find an existing manual payment recorded under this key."""
        result = await session.execute(
            select(Payment).where(
                Payment.provider == "manual",
                Payment.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def record_provider_payment(
        session: AsyncSession,
        invoice_id: int,
        *,
        amount: Decimal | str | int | float,
        currency_code: str,
        provider: str,
        status: str,
        provider_payment_id: str | None = None,
        provider_checkout_id: str | None = None,
        provider_charge_id: str | None = None,
        fee_amount: Decimal | str | int | float | None = None,
        occurred_at: datetime | None = None,
        commit: bool = True,
        allow_ineligible_invoice: bool = False,
    ) -> Payment:
        invoice = await session.get(Invoice, invoice_id)
        if not invoice:
            raise ValueError("Invoice not found")
        if invoice.deleted_at is not None and not allow_ineligible_invoice:
            raise ValueError("Invoice not found")
        normalized_currency = currency_code.upper()
        if normalized_currency != invoice.currency_code.upper():
            raise ValueError("Payment currency does not match invoice currency")

        existing = None
        if provider_payment_id:
            existing = (
                await session.execute(
                    select(Payment).where(
                        Payment.provider == provider,
                        Payment.provider_payment_id == provider_payment_id,
                    )
                )
            ).scalar_one_or_none()
        if not existing and provider_checkout_id:
            existing = (
                await session.execute(
                    select(Payment).where(
                        Payment.provider == provider,
                        Payment.provider_checkout_id == provider_checkout_id,
                    )
                )
            ).scalar_one_or_none()

        if existing:
            if existing.invoice_id != invoice.id or quantize_money(existing.amount) != quantize_money(amount):
                raise ValueError("Provider payment identifier conflicts with existing payment")
            previous_status = existing.status
            if previous_status in TERMINAL_PROVIDER_PAYMENT_STATUSES:
                status = previous_status
            elif previous_status == "failed" and status == "processing":
                # A late checkout-completed event must not resurrect an async
                # payment that the provider has already declared failed.
                status = previous_status
            existing.status = status
            existing.provider_payment_id = provider_payment_id or existing.provider_payment_id
            existing.provider_checkout_id = provider_checkout_id or existing.provider_checkout_id
            existing.provider_charge_id = provider_charge_id or existing.provider_charge_id
            if (
                occurred_at is not None
                and status in SETTLED_PAYMENT_STATUSES | {"needs_review"}
                and previous_status not in SETTLED_PAYMENT_STATUSES | {"needs_review"}
            ):
                existing.occurred_at = ensure_utc(occurred_at)
            existing.updated_at = utc_now()
            payment = existing
        else:
            payment = Payment(
                invoice_id=invoice.id,
                amount=quantize_money(amount),
                refunded_amount=Decimal("0.00"),
                fee_amount=quantize_money(fee_amount) if fee_amount is not None else None,
                currency_code=normalized_currency,
                provider=provider,
                status=status,
                provider_payment_id=provider_payment_id,
                provider_checkout_id=provider_checkout_id,
                provider_charge_id=provider_charge_id,
                occurred_at=ensure_utc(occurred_at) or utc_now(),
            )
            session.add(payment)
            await session.flush()

        if not allow_ineligible_invoice:
            await PaymentService._sync_invoice_state(session, invoice)
        if commit:
            await session.commit()
            await session.refresh(payment)
        else:
            await session.flush()
        return payment

    @staticmethod
    async def refund_payment(
        session: AsyncSession,
        payment_id: int,
        amount: Decimal | str | int | float,
        *,
        occurred_at: datetime | None = None,
        notes: str | None = None,
        idempotency_key: str,
    ) -> Payment:
        idempotency_key = idempotency_key.strip()
        if not (8 <= len(idempotency_key) <= 255):
            raise ValueError("Refund idempotency key must be 8-255 characters")
        payment = await session.get(Payment, payment_id)
        if not payment:
            raise ValueError("Payment not found")
        if payment.status not in SETTLED_PAYMENT_STATUSES:
            raise ValueError("Only settled payments can be refunded")

        refund_amount = quantize_money(amount)
        existing_refund = (
            await session.execute(
                select(PaymentRefund).where(
                    PaymentRefund.provider == "manual",
                    PaymentRefund.provider_event_id == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing_refund:
            if (
                existing_refund.payment_id != payment.id
                or quantize_money(existing_refund.amount) != refund_amount
            ):
                raise ValueError(
                    "Refund idempotency key was already used for a different refund"
                )
            await session.refresh(payment)
            return payment
        remaining = quantize_money(payment.amount - (payment.refunded_amount or 0))
        if refund_amount <= 0 or refund_amount > remaining:
            raise ValueError(f"Refund must be between 0.01 and {remaining}")

        new_refunded_amount = Payment.refunded_amount + refund_amount
        values = {
            "refunded_amount": new_refunded_amount,
            "status": case(
                (new_refunded_amount == Payment.amount, "refunded"),
                else_="partially_refunded",
            ),
            "updated_at": utc_now(),
        }
        if notes:
            values["notes"] = notes
        claimed = await session.execute(
            update(Payment)
            .where(
                Payment.id == payment.id,
                Payment.status.in_(SETTLED_PAYMENT_STATUSES),
                new_refunded_amount <= Payment.amount,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            replay = (
                await session.execute(
                    select(PaymentRefund).where(
                        PaymentRefund.provider == "manual",
                        PaymentRefund.provider_event_id == idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if replay:
                if (
                    replay.payment_id != payment.id
                    or quantize_money(replay.amount) != refund_amount
                ):
                    raise ValueError(
                        "Refund idempotency key was already used for a different refund"
                    )
                await session.refresh(payment)
                return payment
            await session.refresh(payment)
            remaining = quantize_money(
                payment.amount - (payment.refunded_amount or 0)
            )
            raise ValueError(f"Refund must be between 0.01 and {remaining}")
        await session.refresh(payment)
        session.add(
            PaymentRefund(
                payment_id=payment.id,
                amount=refund_amount,
                currency_code=payment.currency_code,
                provider="manual",
                provider_event_id=idempotency_key,
                notes=notes,
                occurred_at=ensure_utc(occurred_at) or utc_now(),
            )
        )

        invoice = await session.get(Invoice, payment.invoice_id)
        await PaymentService._sync_invoice_state(session, invoice)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            replay = (
                await session.execute(
                    select(PaymentRefund).where(
                        PaymentRefund.provider == "manual",
                        PaymentRefund.provider_event_id == idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if (
                not replay
                or replay.payment_id != payment_id
                or quantize_money(replay.amount) != refund_amount
            ):
                raise
            payment = await session.get(Payment, payment_id, populate_existing=True)
        await session.refresh(payment)
        return payment

    @staticmethod
    async def set_online_payment_enabled(
        session: AsyncSession, invoice_id: int, enabled: bool, *, rotate_token: bool = False
    ) -> Invoice:
        invoice = await session.get(Invoice, invoice_id)
        if not invoice or invoice.deleted_at is not None:
            raise ValueError("Invoice not found")
        if invoice.document_type != "invoice":
            raise ValueError("Online payment cannot be enabled for quotes")

        if (not enabled or rotate_token) and invoice.payment_checkout_idempotency_key:
            await PaymentService.expire_active_checkout(session, invoice)

        invoice.online_payment_enabled = 1 if enabled else 0
        if enabled and (not invoice.payment_token or rotate_token):
            invoice.payment_token = secrets.token_urlsafe(48)
        elif not enabled and rotate_token:
            invoice.payment_token = None
        if not enabled or rotate_token:
            invoice.payment_checkout_provider = None
            invoice.payment_checkout_id = None
            invoice.payment_checkout_url = None
            invoice.payment_checkout_amount = None
            invoice.payment_checkout_currency = None
            invoice.payment_checkout_idempotency_key = None
            invoice.payment_checkout_fingerprint = None
            invoice.payment_checkout_expires_at = None
        invoice.updated_at = utc_now()
        await session.commit()
        await session.refresh(invoice)
        return invoice

    @staticmethod
    async def process_provider_event(
        session: AsyncSession,
        provider: str,
        event: ProviderEvent,
        payload_digest: str,
    ) -> dict:
        """Apply one verified provider event exactly once in one transaction."""
        existing = (
            await session.execute(
                select(PaymentEvent).where(
                    PaymentEvent.provider == provider,
                    PaymentEvent.event_id == event.id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            if existing.status != "failed":
                return {"processed": False, "duplicate": True}
            audit = existing
            audit.status = "processing"
            audit.error = None
        else:
            audit = PaymentEvent(
                provider=provider,
                event_id=event.id,
                event_type=event.type,
                payload_digest=payload_digest,
                status="processing",
            )
            session.add(audit)

        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            return {"processed": False, "duplicate": True}

        try:
            if event.type in {
                "checkout.session.completed",
                "checkout.session.async_payment_succeeded",
                "checkout.session.async_payment_failed",
            }:
                await PaymentService._process_checkout_event(session, provider, event)
            elif event.type == "charge.refunded":
                await PaymentService._process_refund_event(session, provider, event)
            elif event.type in {"charge.dispute.created", "charge.dispute.closed"}:
                await PaymentService._process_dispute_event(session, provider, event)
            else:
                audit.status = "ignored"
                await session.commit()
                return {"processed": True, "ignored": True}

            audit.status = "processed"
            audit.processed_at = utc_now()
            await session.commit()
            return {"processed": True, "duplicate": False}
        except Exception as exc:
            await session.rollback()
            failed = (
                await session.execute(
                    select(PaymentEvent).where(
                        PaymentEvent.provider == provider,
                        PaymentEvent.event_id == event.id,
                    )
                )
            ).scalar_one_or_none()
            if not failed:
                failed = PaymentEvent(
                    provider=provider,
                    event_id=event.id,
                    event_type=event.type,
                    payload_digest=payload_digest,
                )
                session.add(failed)
            failed.status = "failed"
            failed.error = str(exc)[:2000]
            failed.processed_at = utc_now()
            await session.commit()
            raise ValueError(f"Could not process {provider} event {event.id}: {exc}") from exc

    @staticmethod
    async def _process_checkout_event(
        session: AsyncSession, provider: str, event: ProviderEvent
    ) -> None:
        data = event.data
        metadata = data.get("metadata") or {}
        try:
            invoice_id = int(metadata["invoice_id"])
            amount_minor = int(data["amount_total"])
            expected_minor = int(metadata["expected_amount_minor"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Checkout event is missing trusted invoice metadata") from exc
        currency = str(data.get("currency") or "").upper()
        expected_currency = str(metadata.get("currency_code") or "").upper()
        if amount_minor != expected_minor or currency != expected_currency:
            raise ValueError("Checkout amount or currency does not match signed metadata")

        invoice = await session.get(Invoice, invoice_id)
        if not invoice:
            raise ValueError("Checkout references an unknown invoice")
        amount = from_minor_units(amount_minor, currency)
        summary = await PaymentService.payment_summary(session, invoice)
        invoice_is_eligible = (
            invoice.deleted_at is None
            and invoice.document_type == "invoice"
            and invoice.status in {"sent", "overdue", "partially_paid"}
        )

        if event.type == "checkout.session.async_payment_failed":
            status = "failed"
        elif event.type == "checkout.session.async_payment_succeeded":
            status = "succeeded"
        elif data.get("payment_status") == "paid":
            status = "succeeded"
        else:
            status = "processing"

        # A payment completed from an old browser tab after a manual payment or
        # invoice edit is retained for reconciliation but never silently applied.
        if status == "succeeded" and (
            not invoice_is_eligible or amount > summary["outstanding"]
        ):
            status = "needs_review"

        payment_intent = data.get("payment_intent")
        if isinstance(payment_intent, dict):
            payment_intent = payment_intent.get("id")
        await PaymentService.record_provider_payment(
            session,
            invoice_id,
            amount=amount,
            currency_code=currency,
            provider=provider,
            status=status,
            provider_payment_id=str(payment_intent) if payment_intent else None,
            provider_checkout_id=str(data.get("id")) if data.get("id") else None,
            occurred_at=event.occurred_at,
            commit=False,
            allow_ineligible_invoice=not invoice_is_eligible,
        )
        checkout_id = str(data.get("id")) if data.get("id") else None
        if checkout_id and invoice.payment_checkout_id == checkout_id:
            invoice.payment_checkout_provider = None
            invoice.payment_checkout_id = None
            invoice.payment_checkout_url = None
            invoice.payment_checkout_amount = None
            invoice.payment_checkout_currency = None
            invoice.payment_checkout_idempotency_key = None
            invoice.payment_checkout_fingerprint = None
            invoice.payment_checkout_expires_at = None

    @staticmethod
    async def _find_provider_payment(
        session: AsyncSession, provider: str, provider_payment_id: str | None
    ) -> Payment:
        if not provider_payment_id:
            raise ValueError("Provider event has no payment identifier")
        payment = (
            await session.execute(
                select(Payment).where(
                    Payment.provider == provider,
                    Payment.provider_payment_id == provider_payment_id,
                )
            )
        ).scalar_one_or_none()
        if not payment:
            raise ValueError("Provider event references an unknown payment")
        return payment

    @staticmethod
    async def _process_refund_event(
        session: AsyncSession, provider: str, event: ProviderEvent
    ) -> None:
        data = event.data
        payment_intent = data.get("payment_intent")
        if isinstance(payment_intent, dict):
            payment_intent = payment_intent.get("id")
        payment = await PaymentService._find_provider_payment(
            session, provider, str(payment_intent) if payment_intent else None
        )
        refunded = from_minor_units(int(data.get("amount_refunded", 0)), payment.currency_code)
        if refunded < 0 or refunded > payment.amount:
            raise ValueError("Provider refund amount is invalid")
        previous_refunded = quantize_money(payment.refunded_amount or 0)
        if refunded < previous_refunded:
            return
        refund_delta = quantize_money(refunded - previous_refunded)
        if refund_delta > 0:
            session.add(
                PaymentRefund(
                    payment_id=payment.id,
                    amount=refund_delta,
                    currency_code=payment.currency_code,
                    provider=provider,
                    provider_event_id=event.id,
                    occurred_at=ensure_utc(event.occurred_at) or utc_now(),
                )
            )
        payment.refunded_amount = refunded
        payment.status = "refunded" if refunded == payment.amount else "partially_refunded"
        payment.updated_at = utc_now()
        invoice = await session.get(Invoice, payment.invoice_id)
        await PaymentService._sync_invoice_state(session, invoice)

    @staticmethod
    async def _process_dispute_event(
        session: AsyncSession, provider: str, event: ProviderEvent
    ) -> None:
        data = event.data
        payment_intent = data.get("payment_intent")
        if isinstance(payment_intent, dict):
            payment_intent = payment_intent.get("id")
        payment = await PaymentService._find_provider_payment(
            session, provider, str(payment_intent) if payment_intent else None
        )
        try:
            event_amount = from_minor_units(int(data["amount"]), payment.currency_code)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Dispute event has no valid amount") from exc
        available = quantize_money(payment.amount - (payment.refunded_amount or 0))
        if event_amount <= 0 or event_amount > available:
            raise ValueError("Provider dispute amount is invalid")

        current_disputed = quantize_money(payment.disputed_amount or 0)
        cash_delta = Decimal("0.00")
        adjustment_kind = None
        if event.type == "charge.dispute.created":
            if event_amount > current_disputed:
                cash_delta = -quantize_money(event_amount - current_disputed)
                adjustment_kind = "dispute_opened"
            payment.disputed_amount = event_amount
            payment.dispute_status = "open"
        elif data.get("status") == "won":
            if current_disputed > 0:
                cash_delta = current_disputed
                adjustment_kind = "dispute_reversed"
            payment.disputed_amount = Decimal("0.00")
            payment.dispute_status = None
        else:
            # If the opening event was missed, the terminal lost event still
            # records the chargeback in the period when it became known.
            if current_disputed == 0:
                cash_delta = -event_amount
                adjustment_kind = "dispute_opened"
            payment.disputed_amount = event_amount
            payment.dispute_status = "lost"

        if cash_delta:
            session.add(
                PaymentAdjustment(
                    payment_id=payment.id,
                    amount=cash_delta,
                    currency_code=payment.currency_code,
                    provider=provider,
                    kind=adjustment_kind,
                    provider_event_id=event.id,
                    occurred_at=ensure_utc(event.occurred_at) or utc_now(),
                )
            )
        payment.updated_at = utc_now()
        invoice = await session.get(Invoice, payment.invoice_id)
        await PaymentService._sync_invoice_state(session, invoice)
    @staticmethod
    def summarize(invoice: Invoice, payments: list[Payment]) -> dict:
        """Calculate a balance summary from already-loaded payment records."""
        paid = Decimal("0.00")
        refunded = Decimal("0.00")
        pending = Decimal("0.00")
        disputed = Decimal("0.00")

        for payment in payments:
            amount = quantize_money(payment.amount)
            refunded_amount = quantize_money(payment.refunded_amount or 0)
            disputed_amount = min(
                max(Decimal("0.00"), quantize_money(payment.disputed_amount or 0)),
                max(Decimal("0.00"), amount - refunded_amount),
            )
            refunded += refunded_amount
            disputed += disputed_amount
            if payment.status in SETTLED_PAYMENT_STATUSES:
                paid += max(
                    Decimal("0.00"), amount - refunded_amount - disputed_amount
                )
            elif payment.status in {"pending", "processing"}:
                pending += amount

        total = quantize_money(invoice.total or 0)
        paid = quantize_money(paid)
        return {
            "total": total,
            "paid": paid,
            "outstanding": quantize_money(max(Decimal("0.00"), total - paid)),
            "refunded": quantize_money(refunded),
            "pending": quantize_money(pending),
            "disputed": quantize_money(disputed),
            "currency_code": invoice.currency_code,
        }
    @staticmethod
    async def expire_active_checkout(session: AsyncSession, invoice: Invoice) -> None:
        """Expire and forget an active provider Checkout session."""
        claim_key = invoice.payment_checkout_idempotency_key
        if not claim_key:
            return
        if not invoice.payment_checkout_provider or not invoice.payment_checkout_id:
            raise ValueError(
                "The active Checkout session is still being created; retry shortly"
            )
        from invoice_machine.payments.registry import get_provider_for_existing_payment

        profile = await BusinessProfile.get(session)
        if not profile:
            raise ValueError("Payment provider settings are not configured")
        try:
            provider = get_provider_for_existing_payment(
                profile, invoice.payment_checkout_provider
            )
            await provider.expire_checkout(invoice.payment_checkout_id)
        except PaymentProviderError as exc:
            raise ValueError(f"Could not revoke the active Checkout session: {exc}") from exc

        await session.execute(
            update(Invoice)
            .where(
                Invoice.id == invoice.id,
                Invoice.payment_checkout_idempotency_key == claim_key,
            )
            .values(
                payment_checkout_provider=None,
                payment_checkout_id=None,
                payment_checkout_url=None,
                payment_checkout_amount=None,
                payment_checkout_currency=None,
                payment_checkout_idempotency_key=None,
                payment_checkout_fingerprint=None,
                payment_checkout_expires_at=None,
            )
        )
        await session.flush()
        await session.refresh(invoice)
