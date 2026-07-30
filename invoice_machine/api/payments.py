"""Payments API endpoints (partial payments and A/R aging)."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import get_session
from invoice_machine.presenters import serialize_payment
from invoice_machine.rate_limit import limiter
from invoice_machine.services import InvoiceService, PaymentService

router = APIRouter(tags=["payments"])


class PaymentSchema(BaseModel):
    """A recorded payment."""

    id: int
    invoice_id: int
    amount: str
    currency_code: str
    payment_date: date
    method: str | None = None
    reference: str | None = None
    notes: str | None = None
    provider: str | None = None
    external_id: str | None = None


class PaymentCreate(BaseModel):
    """Record a payment against an invoice."""

    amount: Decimal = Field(..., gt=0, le=Decimal("99999999.99"))
    payment_date: date | None = None
    method: str | None = Field(None, max_length=50)
    reference: str | None = Field(None, max_length=255)
    notes: str | None = Field(None, max_length=2000)
    # Explicit opt-in so a fat-fingered amount can't silently overpay an invoice.
    allow_overpayment: bool = False


class PaymentUpdate(BaseModel):
    """Update a recorded payment."""

    amount: Decimal | None = Field(None, gt=0, le=Decimal("99999999.99"))
    payment_date: date | None = None
    method: str | None = Field(None, max_length=50)
    reference: str | None = Field(None, max_length=255)
    notes: str | None = Field(None, max_length=2000)


class InvoicePaymentsResponse(BaseModel):
    """Payments for an invoice plus the resulting balance."""

    invoice_id: int
    currency_code: str
    total: str
    amount_paid: str
    amount_due: str
    is_partially_paid: bool
    payments: list[PaymentSchema]


@router.get("/api/invoices/{invoice_id}/payments", response_model=InvoicePaymentsResponse)
@limiter.limit("120/minute")
async def list_invoice_payments(
    request: Request,
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """List payments recorded against an invoice."""
    invoice = await InvoiceService.get_invoice(session, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    payments = await PaymentService.list_payments(session, invoice_id)
    return {
        "invoice_id": invoice.id,
        "currency_code": invoice.currency_code,
        "total": str(invoice.total),
        "amount_paid": str(invoice.amount_paid or 0),
        "amount_due": str(invoice.amount_due),
        "is_partially_paid": invoice.is_partially_paid,
        "payments": [serialize_payment(payment) for payment in payments],
    }


@router.post(
    "/api/invoices/{invoice_id}/payments",
    response_model=InvoicePaymentsResponse,
    status_code=201,
)
@limiter.limit("60/minute")
async def record_payment(
    request: Request,
    invoice_id: int,
    data: PaymentCreate,
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    """Record a (possibly partial) payment against an invoice.

    Send an ``Idempotency-Key`` header to make a retry safe: replaying the same
    key returns the payment already recorded rather than adding a second one.
    Optional rather than required, because this is the browser path and the
    existing UI does not send one.
    """
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not (8 <= len(idempotency_key) <= 255):
            raise HTTPException(
                status_code=400,
                detail="Idempotency-Key must be 8-255 characters",
            )

    try:
        payment = await PaymentService.record_payment(
            session,
            invoice_id,
            amount=data.amount,
            payment_date=data.payment_date,
            method=data.method,
            reference=data.reference,
            notes=data.notes,
            allow_overpayment=data.allow_overpayment,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    if payment is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return await list_invoice_payments(request, invoice_id, session)


@router.put("/api/payments/{payment_id}", response_model=InvoicePaymentsResponse)
@limiter.limit("60/minute")
async def update_payment(
    request: Request,
    payment_id: int,
    data: PaymentUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update a recorded payment."""
    try:
        payment = await PaymentService.update_payment(
            session, payment_id, **data.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")

    return await list_invoice_payments(request, payment.invoice_id, session)


@router.delete("/api/payments/{payment_id}", status_code=204)
@limiter.limit("60/minute")
async def delete_payment(
    request: Request,
    payment_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete a recorded payment and resync the invoice balance."""
    deleted = await PaymentService.delete_payment(session, payment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Payment not found")


class PaymentLinkResponse(BaseModel):
    """A hosted payment link for an invoice."""

    invoice_id: int
    payment_link_url: str
    amount_due: str
    currency_code: str
    provider: str


@router.post("/api/invoices/{invoice_id}/payment-link", response_model=PaymentLinkResponse)
@limiter.limit("30/hour")
async def create_payment_link(
    request: Request,
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create (or refresh) a hosted payment link for an invoice's balance."""
    from invoice_machine.config import get_settings
    from invoice_machine.database import BusinessProfile
    from invoice_machine.service.stripe_links import StripeError
    from invoice_machine.service.stripe_links import (
        create_payment_link as create_stripe_link,
    )
    from invoice_machine.utils import utc_now

    invoice = await InvoiceService.get_invoice(session, invoice_id)
    if not invoice or invoice.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    profile = await BusinessProfile.get_or_create(session)
    if not profile.payments_enabled:
        raise HTTPException(
            status_code=400,
            detail="Online payments are not enabled. Configure them in settings.",
        )
    if (profile.payments_provider or "stripe") != "stripe":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported payment provider: {profile.payments_provider}",
        )
    if invoice.amount_due <= 0:
        raise HTTPException(status_code=400, detail="Invoice has no outstanding balance")

    base_url = (profile.app_base_url or get_settings().app_base_url or "").rstrip("/")
    try:
        link = await create_stripe_link(
            profile,
            invoice,
            success_url=f"{base_url}/invoices/{invoice.id}?payment=success",
            cancel_url=f"{base_url}/invoices/{invoice.id}?payment=cancelled",
        )
    except StripeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    invoice.payment_link_url = link["url"]
    invoice.payment_link_id = link["id"]
    invoice.payment_link_created_at = utc_now()
    await session.commit()

    return {
        "invoice_id": invoice.id,
        "payment_link_url": link["url"],
        "amount_due": str(invoice.amount_due),
        "currency_code": invoice.currency_code,
        "provider": "stripe",
    }


@router.get("/api/analytics/aging")
@limiter.limit("30/minute")
async def aging_report(
    request: Request,
    as_of: date | None = Query(None, description="Report date (defaults to today, UTC)"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Accounts-receivable aging by overdue bucket, grouped per currency."""
    return await PaymentService.aging_report(session, as_of=as_of)
