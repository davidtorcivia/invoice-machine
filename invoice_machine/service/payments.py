"""Payment recording and partial-payment bookkeeping.

An invoice's ``amount_paid`` is a denormalized cache of this table. Every mutation
goes through :func:`recalculate_invoice_payments`, which is the single place that
recomputes the cache and drives the paid/unpaid status transition — so the two can
never drift apart.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import Invoice, Payment
from invoice_machine.service.common import quantize_money
from invoice_machine.utils import utc_now

_UNPAYABLE_STATUSES = ("cancelled",)


def _coerce_amount(value: Decimal | float | int | str) -> Decimal:
    """Coerce a payment amount to a positive, cent-quantized Decimal."""
    try:
        amount = quantize_money(value)
    except (InvalidOperation, ArithmeticError, ValueError, TypeError):
        raise ValueError("Payment amount must be a number") from None
    if not amount.is_finite():
        raise ValueError("Payment amount must be a finite number")
    if amount <= 0:
        raise ValueError("Payment amount must be greater than 0")
    return amount


async def recalculate_invoice_payments(session: AsyncSession, invoice: Invoice) -> Invoice:
    """Recompute ``amount_paid`` from the payments table and sync invoice status.

    Status rules (deliberately conservative — a payment never resurrects a
    cancelled invoice and never promotes a draft):
    - fully paid  -> "paid", stamping paid_at with the latest payment date
    - was paid but no longer fully paid -> back to "sent"/"overdue", paid_at cleared
    - partially paid -> status untouched; the balance lives in amount_due
    """
    total_paid = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.invoice_id == invoice.id
            )
        )
    ).scalar() or 0
    invoice.amount_paid = quantize_money(total_paid)

    invoice_total = quantize_money(invoice.total or 0)
    fully_paid = invoice_total > 0 and invoice.amount_paid >= invoice_total

    if invoice.status not in _UNPAYABLE_STATUSES:
        if fully_paid and invoice.status != "paid":
            if invoice.status != "draft":
                invoice.status = "paid"
                invoice.paid_at = utc_now()
        elif not fully_paid and invoice.status == "paid":
            # Reverted (payment deleted or invoice total raised): fall back to
            # overdue when past due, otherwise sent.
            today = utc_now().date()
            invoice.status = (
                "overdue" if invoice.due_date and invoice.due_date < today else "sent"
            )
            invoice.paid_at = None

    invoice.updated_at = utc_now()
    return invoice


class PaymentService:
    """Service for recording and querying invoice payments."""

    @staticmethod
    async def list_payments(session: AsyncSession, invoice_id: int) -> list[Payment]:
        """List payments for an invoice, oldest first."""
        result = await session.execute(
            select(Payment)
            .where(Payment.invoice_id == invoice_id)
            .order_by(Payment.payment_date, Payment.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_payment(session: AsyncSession, payment_id: int) -> Payment | None:
        """Get a payment by ID."""
        return await session.get(Payment, payment_id)

    @staticmethod
    async def find_by_external_id(
        session: AsyncSession, provider: str, external_id: str
    ) -> Payment | None:
        """Look up a provider-created payment, for webhook idempotency."""
        result = await session.execute(
            select(Payment).where(
                Payment.provider == provider, Payment.external_id == external_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def record_payment(
        session: AsyncSession,
        invoice_id: int,
        amount: Decimal | float | int | str,
        payment_date: date | None = None,
        method: str | None = None,
        reference: str | None = None,
        notes: str | None = None,
        provider: str | None = None,
        external_id: str | None = None,
        allow_overpayment: bool = False,
    ) -> Payment | None:
        """Record a payment against an invoice.

        Returns None when the invoice does not exist so callers can map that to a
        404. Raises ValueError for caller errors (bad amount, cancelled invoice,
        overpayment without an explicit opt-in).
        """
        invoice = await session.get(Invoice, invoice_id)
        if invoice is None or invoice.deleted_at is not None:
            return None

        if invoice.status in _UNPAYABLE_STATUSES:
            raise ValueError(f"Cannot record a payment against a {invoice.status} invoice")

        payment_amount = _coerce_amount(amount)

        if not allow_overpayment:
            outstanding = invoice.amount_due
            if payment_amount > outstanding:
                raise ValueError(
                    f"Payment of {payment_amount} exceeds the outstanding balance "
                    f"of {outstanding}. Pass allow_overpayment to record it anyway."
                )

        # A provider event that already landed must not be recorded twice.
        if provider and external_id:
            existing = await PaymentService.find_by_external_id(session, provider, external_id)
            if existing is not None:
                return existing

        payment = Payment(
            invoice_id=invoice_id,
            amount=payment_amount,
            # Snapshot the invoice currency; payments are never cross-currency.
            currency_code=invoice.currency_code,
            payment_date=payment_date or utc_now().date(),
            method=method,
            reference=reference,
            notes=notes,
            provider=provider,
            external_id=external_id,
        )
        session.add(payment)
        await session.flush()

        await recalculate_invoice_payments(session, invoice)
        await session.commit()
        await session.refresh(payment)
        return payment

    @staticmethod
    async def update_payment(
        session: AsyncSession,
        payment_id: int,
        amount: Decimal | float | int | str | None = None,
        payment_date: date | None = None,
        method: str | None = None,
        reference: str | None = None,
        notes: str | None = None,
    ) -> Payment | None:
        """Update a recorded payment and resync the invoice."""
        payment = await session.get(Payment, payment_id)
        if payment is None:
            return None

        if amount is not None:
            payment.amount = _coerce_amount(amount)
        if payment_date is not None:
            payment.payment_date = payment_date
        if method is not None:
            payment.method = method
        if reference is not None:
            payment.reference = reference
        if notes is not None:
            payment.notes = notes

        await session.flush()

        invoice = await session.get(Invoice, payment.invoice_id)
        if invoice is not None:
            await recalculate_invoice_payments(session, invoice)

        await session.commit()
        await session.refresh(payment)
        return payment

    @staticmethod
    async def delete_payment(session: AsyncSession, payment_id: int) -> bool:
        """Delete a payment (hard delete) and resync the invoice."""
        payment = await session.get(Payment, payment_id)
        if payment is None:
            return False

        invoice_id = payment.invoice_id
        await session.execute(delete(Payment).where(Payment.id == payment_id))
        await session.flush()

        invoice = await session.get(Invoice, invoice_id)
        if invoice is not None:
            await recalculate_invoice_payments(session, invoice)

        await session.commit()
        return True

    @staticmethod
    async def aging_report(session: AsyncSession, as_of: date | None = None) -> dict:
        """Accounts-receivable aging, bucketed by how overdue each invoice is.

        Buckets hold the *outstanding* balance (total minus payments), grouped by
        currency — amounts in different currencies are never added together.
        Drafts, quotes, cancelled and fully-paid invoices are excluded.
        """
        today = as_of or utc_now().date()

        rows = (
            await session.execute(
                select(
                    Invoice.id,
                    Invoice.invoice_number,
                    Invoice.currency_code,
                    Invoice.client_id,
                    Invoice.client_name,
                    Invoice.client_business,
                    Invoice.due_date,
                    Invoice.total,
                    Invoice.amount_paid,
                ).where(
                    Invoice.document_type == "invoice",
                    Invoice.deleted_at.is_(None),
                    Invoice.status.in_(("sent", "overdue")),
                )
            )
        ).all()

        bucket_names = ("current", "1_30", "31_60", "61_90", "over_90")
        by_currency: dict[str, dict] = {}
        invoices: list[dict] = []

        for row in rows:
            outstanding = quantize_money(row.total or 0) - quantize_money(row.amount_paid or 0)
            if outstanding <= 0:
                continue

            days_overdue = (today - row.due_date).days if row.due_date else 0
            if days_overdue <= 0:
                bucket = "current"
            elif days_overdue <= 30:
                bucket = "1_30"
            elif days_overdue <= 60:
                bucket = "31_60"
            elif days_overdue <= 90:
                bucket = "61_90"
            else:
                bucket = "over_90"

            currency = row.currency_code or "USD"
            entry = by_currency.setdefault(
                currency,
                {
                    "buckets": {name: Decimal("0.00") for name in bucket_names},
                    "counts": dict.fromkeys(bucket_names, 0),
                    "total_outstanding": Decimal("0.00"),
                    "invoice_count": 0,
                },
            )
            entry["buckets"][bucket] += outstanding
            entry["counts"][bucket] += 1
            entry["total_outstanding"] += outstanding
            entry["invoice_count"] += 1

            invoices.append({
                "invoice_id": row.id,
                "invoice_number": row.invoice_number,
                "client_id": row.client_id,
                "client_name": row.client_business or row.client_name,
                "currency_code": currency,
                "due_date": row.due_date.isoformat() if row.due_date else None,
                "days_overdue": max(days_overdue, 0),
                "bucket": bucket,
                "total": str(quantize_money(row.total or 0)),
                "amount_paid": str(quantize_money(row.amount_paid or 0)),
                "amount_due": str(outstanding),
            })

        invoices.sort(key=lambda item: (-item["days_overdue"], item["invoice_number"]))

        return {
            "as_of": today.isoformat(),
            "buckets": bucket_names,
            "by_currency": {
                currency: {
                    "buckets": {name: str(value) for name, value in data["buckets"].items()},
                    "counts": data["counts"],
                    "total_outstanding": str(data["total_outstanding"]),
                    "invoice_count": data["invoice_count"],
                }
                for currency, data in by_currency.items()
            },
            "invoices": invoices,
        }
