"""Payment recording MCP tools."""

from __future__ import annotations

from datetime import date

from invoice_machine.presenters import serialize_payment
from invoice_machine.services import InvoiceService, PaymentService

from .annotations import ADDITIVE_IDEMPOTENT, DESTRUCTIVE, READ_ONLY
from .context import get_session, mcp
from .schemas import PaymentLedgerOut


@mcp.tool(annotations=READ_ONLY)
async def list_payments(invoice_id: int) -> PaymentLedgerOut | None:
    """List payments recorded against an invoice, with the resulting balance."""
    async with get_session() as session:
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            return None

        payments = await PaymentService.list_payments(session, invoice_id)
        return {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "currency_code": invoice.currency_code,
            "total": str(invoice.total),
            "amount_paid": str(invoice.amount_paid or 0),
            "amount_due": str(invoice.amount_due),
            "is_partially_paid": invoice.is_partially_paid,
            "payments": [serialize_payment(p, json_ready=True) for p in payments],
        }


@mcp.tool(annotations=ADDITIVE_IDEMPOTENT)
async def record_payment(
    invoice_id: int,
    amount: float | str,
    idempotency_key: str,
    payment_date: str | None = None,
    method: str | None = None,
    reference: str | None = None,
    notes: str | None = None,
    allow_overpayment: bool = False,
) -> dict:
    """
    Record a payment against an invoice. Supports partial payments.

    An invoice becomes "paid" automatically once recorded payments cover its
    total; until then the remaining balance is reported as amount_due.

    Args:
        amount: Payment amount in the invoice's currency (must be > 0)
        idempotency_key: A unique string identifying this payment. Replaying the
            same key returns the payment already recorded instead of adding a
            second one, so a retried call cannot double-record. Use a fresh key
            for a genuinely separate payment of the same amount.
        payment_date: Payment date (ISO format, defaults to today UTC)
        method: How it was paid, e.g. "bank_transfer", "card", "cash", "cheque"
        reference: Bank reference / cheque number / transaction ID
        allow_overpayment: Permit an amount larger than the outstanding balance
    """
    async with get_session() as session:
        try:
            payment = await PaymentService.record_payment(
                session,
                invoice_id,
                amount=amount,
                payment_date=date.fromisoformat(payment_date) if payment_date else None,
                method=method,
                reference=reference,
                notes=notes,
                allow_overpayment=allow_overpayment,
                idempotency_key=idempotency_key,
            )
        except ValueError as exc:
            await session.rollback()
            return {"success": False, "error": str(exc)}

        if payment is None:
            return {"success": False, "error": f"Invoice {invoice_id} not found"}

        invoice = await InvoiceService.get_invoice(session, invoice_id)
        return {
            "success": True,
            "payment": serialize_payment(payment, json_ready=True),
            "invoice_status": invoice.status,
            "amount_paid": str(invoice.amount_paid or 0),
            "amount_due": str(invoice.amount_due),
        }


@mcp.tool(annotations=DESTRUCTIVE)
async def delete_payment(payment_id: int) -> bool:
    """
    Delete a recorded payment and resync the invoice balance.

    If this leaves a previously-paid invoice short, it reverts to sent/overdue.
    """
    async with get_session() as session:
        return await PaymentService.delete_payment(session, payment_id)


@mcp.tool(annotations=READ_ONLY)
async def get_aging_report(as_of: str | None = None) -> dict:
    """
    Accounts-receivable aging: outstanding balances bucketed by how overdue.

    Buckets are current / 1-30 / 31-60 / 61-90 / over 90 days past due, grouped
    per currency (amounts in different currencies are never added together).
    Drafts, quotes, cancelled and fully-paid invoices are excluded.

    Args:
        as_of: Report date (ISO format, defaults to today UTC)
    """
    async with get_session() as session:
        return await PaymentService.aging_report(
            session, as_of=date.fromisoformat(as_of) if as_of else None
        )
