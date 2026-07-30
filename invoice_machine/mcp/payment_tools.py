"""Provider-neutral payment ledger MCP tools."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from mcp.server.mcpserver import Context, Elicit, Resolve

from invoice_machine.config import get_settings
from invoice_machine.database import Invoice, Payment
from invoice_machine.presenters import serialize_payment
from invoice_machine.service.payments import PaymentService

from .annotations import ADDITIVE, OUTWARD_REVERSAL, READ_ONLY, UPDATE
from .confirmations import Confirmation, confirmed, ensure_confirmed
from .context import get_session, mcp
from .schemas import PaymentLedgerOut, PaymentOut


def _summary_json(summary: dict) -> dict:
    return {
        key: str(value) if isinstance(value, Decimal) else value
        for key, value in summary.items()
    }


@mcp.tool(annotations=READ_ONLY)
async def list_invoice_payments(invoice_id: int) -> PaymentLedgerOut:
    """List an invoice's payment history and current balance."""
    async with get_session() as session:
        invoice = await session.get(Invoice, invoice_id)
        if not invoice or invoice.deleted_at is not None:
            raise ValueError("Invoice not found")
        payments = await PaymentService.list_payments(session, invoice_id)
        summary = await PaymentService.payment_summary(session, invoice)
        return {
            "payments": [serialize_payment(item, json_ready=True) for item in payments],
            "summary": _summary_json(summary),
        }


@mcp.tool(annotations=ADDITIVE)
async def record_invoice_payment(
    invoice_id: int,
    amount: float,
    occurred_at: str | None = None,
    notes: str | None = None,
) -> PaymentOut:
    """Record a manual payment. This works without any online provider."""
    async with get_session() as session:
        payment = await PaymentService.record_manual_payment(
            session,
            invoice_id,
            Decimal(str(amount)),
            occurred_at=datetime.fromisoformat(occurred_at) if occurred_at else None,
            notes=notes,
        )
        return serialize_payment(payment, json_ready=True)


async def _confirm_refund(
    payment_id: int,
    amount: float,
    ctx: Context,
) -> Confirmation | Elicit[Confirmation]:
    """Ask before reversing money, quoting the amount against the invoice."""
    async with get_session() as session:
        payment = await session.get(Payment, payment_id)
        invoice = await session.get(Invoice, payment.invoice_id) if payment else None
        number = invoice.invoice_number if invoice else "an unknown invoice"

    return confirmed(
        ctx,
        f"Record a refund of {amount} against payment {payment_id} "
        f"on invoice {number}?",
    )


@mcp.tool(annotations=OUTWARD_REVERSAL)
async def record_invoice_refund(
    payment_id: int,
    amount: float,
    idempotency_key: str,
    confirmation: Annotated[Confirmation, Resolve(_confirm_refund)],
    notes: str | None = None,
    occurred_at: str | None = None,
) -> PaymentOut:
    """Record a full or partial refund against a settled payment.

    Asks the user to confirm first, where the client supports it.
    """
    ensure_confirmed(confirmation, "This refund")

    async with get_session() as session:
        existing = await session.get(Payment, payment_id)
        if not existing:
            raise ValueError("Payment not found")
        if existing.provider != "manual":
            raise ValueError(
                "Provider refunds must be initiated from the authenticated REST/UI flow"
            )
        payment = await PaymentService.refund_payment(
            session,
            payment_id,
            Decimal(str(amount)),
            notes=notes,
            occurred_at=datetime.fromisoformat(occurred_at) if occurred_at else None,
            idempotency_key=idempotency_key,
        )
        return serialize_payment(payment, json_ready=True)


@mcp.tool(annotations=UPDATE)
async def configure_invoice_payment_link(
    invoice_id: int, enabled: bool, rotate_token: bool = False
) -> dict:
    """Enable or disable an optional hosted-provider payment link for one invoice."""
    async with get_session() as session:
        invoice = await PaymentService.set_online_payment_enabled(
            session, invoice_id, enabled, rotate_token=rotate_token
        )
        token = invoice.payment_token if invoice.online_payment_enabled else None
        return {
            "enabled": bool(invoice.online_payment_enabled),
            "payment_url": (
                f"{get_settings().app_base_url.rstrip('/')}/pay/{token}" if token else None
            ),
        }
