"""Optional provider settings and provider-neutral payment ledger endpoints."""

from __future__ import annotations

import hashlib
import html
import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.config import get_settings
from invoice_machine.crypto import encrypt_credential
from invoice_machine.database import (
    BusinessProfile,
    Invoice,
    Payment,
    ProviderRefundRequest,
    get_session,
)
from invoice_machine.payments import (
    get_payment_provider,
    get_provider_for_existing_payment,
    get_stripe_webhook_provider,
)
from invoice_machine.payments.base import CheckoutRequest, PaymentProviderError, RefundRequest
from invoice_machine.payments.currency import to_minor_units
from invoice_machine.presenters import serialize_payment
from invoice_machine.rate_limit import limiter
from invoice_machine.service.common import quantize_money
from invoice_machine.service.payments import PaymentService
from invoice_machine.utils import ensure_utc, utc_now

router = APIRouter(prefix="/api/payments", tags=["payments"])
public_router = APIRouter(tags=["payments"])
settings = get_settings()


class PaymentSettingsUpdate(BaseModel):
    online_payments_enabled: bool | None = None
    payment_provider: str | None = Field(None, pattern="^(stripe)?$")
    stripe_secret_key: str | None = Field(None, max_length=500)
    stripe_webhook_secret: str | None = Field(None, max_length=500)


class ManualPaymentCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    occurred_at: datetime | None = None
    notes: str | None = Field(None, max_length=2000)


class RefundCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    occurred_at: datetime | None = None
    notes: str | None = Field(None, max_length=2000)


class OnlinePaymentUpdate(BaseModel):
    enabled: bool
    rotate_token: bool = False


def _settings_response(profile: BusinessProfile) -> dict:
    return {
        "online_payments_enabled": bool(profile.online_payments_enabled),
        "payment_provider": profile.payment_provider,
        "stripe_secret_key_set": bool(profile.stripe_secret_key),
        "stripe_webhook_secret_set": bool(profile.stripe_webhook_secret),
    }


@router.get("/settings")
async def get_payment_settings(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await BusinessProfile.get_or_create(session)
    return _settings_response(profile)


@router.put("/settings")
@limiter.limit("20/minute")
async def update_payment_settings(
    request: Request,
    updates: PaymentSettingsUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    profile = await BusinessProfile.get_or_create(session)
    values = updates.model_dump(exclude_unset=True)

    if "payment_provider" in values:
        profile.payment_provider = values["payment_provider"] or None
    if "stripe_secret_key" in values:
        raw = values["stripe_secret_key"]
        profile.stripe_secret_key = encrypt_credential(raw) if raw else None
    if "stripe_webhook_secret" in values:
        raw = values["stripe_webhook_secret"]
        profile.stripe_webhook_secret = encrypt_credential(raw) if raw else None
    if "online_payments_enabled" in values:
        if values["online_payments_enabled"] and not profile.payment_provider:
            raise HTTPException(status_code=400, detail="Choose a payment provider first")
        profile.online_payments_enabled = 1 if values["online_payments_enabled"] else 0

    await session.commit()
    await session.refresh(profile)
    return _settings_response(profile)


@router.post("/settings/test")
@limiter.limit("10/minute")
async def test_payment_provider(
    request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    profile = await BusinessProfile.get_or_create(session)
    try:
        provider = get_payment_provider(profile)
        return await provider.test_connection()
    except PaymentProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/invoices/{invoice_id}")
async def list_invoice_payments(
    invoice_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    invoice = await session.get(Invoice, invoice_id)
    if not invoice or invoice.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    payments = await PaymentService.list_payments(session, invoice_id)
    summary = await PaymentService.payment_summary(session, invoice)
    return {
        "payments": [serialize_payment(payment, json_ready=True) for payment in payments],
        "summary": {key: str(value) if isinstance(value, Decimal) else value for key, value in summary.items()},
    }


@router.post("/invoices/{invoice_id}/manual", status_code=201)
@limiter.limit("30/minute")
async def create_manual_payment(
    request: Request,
    invoice_id: int,
    data: ManualPaymentCreate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        payment = await PaymentService.record_manual_payment(
            session,
            invoice_id,
            data.amount,
            occurred_at=data.occurred_at,
            notes=data.notes,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_payment(payment, json_ready=True)


@router.post("/{payment_id}/refund")
@limiter.limit("30/minute")
async def refund_payment(
    request: Request,
    payment_id: int,
    data: RefundCreate,
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    payment = await session.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if not idempotency_key or not (8 <= len(idempotency_key.strip()) <= 255):
        raise HTTPException(
            status_code=400,
            detail="Refunds require an Idempotency-Key header (8-255 characters)",
        )
    idempotency_key = idempotency_key.strip()
    if payment.provider != "manual":
        provider_name = payment.provider
        provider_payment_id = payment.provider_payment_id
        payment_currency = payment.currency_code
        stable_payment_id = payment.id
        if not payment.provider_payment_id:
            raise HTTPException(status_code=409, detail="Provider payment has no refundable ID")
        refund_amount = quantize_money(data.amount)
        remaining = quantize_money(
            Decimal(payment.amount) - Decimal(payment.refunded_amount or 0)
        )
        refund_request = (
            await session.execute(
                select(ProviderRefundRequest).where(
                    ProviderRefundRequest.provider == provider_name,
                    ProviderRefundRequest.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if refund_request:
            if (
                refund_request.payment_id != stable_payment_id
                or quantize_money(refund_request.amount) != refund_amount
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was already used for a different refund",
                )
            if refund_request.status == "submitted":
                return {
                    **serialize_payment(payment, json_ready=True),
                    "refund_initiated": True,
                    "provider_refund_id": refund_request.provider_refund_id,
                    "provider_refund_status": refund_request.provider_refund_status,
                }
        if refund_amount > remaining:
            raise HTTPException(status_code=400, detail=f"Refund exceeds {remaining}")
        if refund_request:
            refund_request.status = "processing"
            refund_request.error = None
            refund_request.updated_at = utc_now()
        else:
            refund_request = ProviderRefundRequest(
                payment_id=payment.id,
                provider=provider_name,
                idempotency_key=idempotency_key,
                amount=refund_amount,
                status="processing",
            )
            session.add(refund_request)
        try:
            # Commit the key before the network call so a timeout or process
            # restart cannot lose the identity of the external operation.
            await session.commit()
        except IntegrityError:
            await session.rollback()
            refund_request = (
                await session.execute(
                    select(ProviderRefundRequest).where(
                        ProviderRefundRequest.provider == provider_name,
                        ProviderRefundRequest.idempotency_key == idempotency_key,
                    )
                )
            ).scalar_one()
            if (
                refund_request.payment_id != stable_payment_id
                or quantize_money(refund_request.amount) != refund_amount
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was already used for a different refund",
                )
            payment = await session.get(Payment, stable_payment_id, populate_existing=True)
            if not payment:
                raise HTTPException(status_code=404, detail="Payment not found")
            if refund_request.status == "submitted":
                return {
                    **serialize_payment(payment, json_ready=True),
                    "refund_initiated": True,
                    "provider_refund_id": refund_request.provider_refund_id,
                    "provider_refund_status": refund_request.provider_refund_status,
                }
        profile = await BusinessProfile.get_or_create(session)
        try:
            provider = get_provider_for_existing_payment(profile, provider_name)
            result = await provider.create_refund(
                RefundRequest(
                    provider_payment_id=provider_payment_id,
                    amount_minor=to_minor_units(refund_amount, payment_currency),
                    idempotency_key=idempotency_key,
                )
            )
        except (PaymentProviderError, ValueError) as exc:
            refund_request.status = "failed"
            refund_request.error = str(exc)[:2000]
            refund_request.updated_at = utc_now()
            await session.commit()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        refund_request.status = "submitted"
        refund_request.provider_refund_id = result.id
        refund_request.provider_refund_status = result.status
        refund_request.error = None
        refund_request.updated_at = utc_now()
        await session.commit()
        return {
            **serialize_payment(payment, json_ready=True),
            "refund_initiated": True,
            "provider_refund_id": result.id,
            "provider_refund_status": result.status,
        }
    try:
        payment = await PaymentService.refund_payment(
            session,
            payment_id,
            data.amount,
            occurred_at=data.occurred_at,
            notes=data.notes,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_payment(payment, json_ready=True)


@router.put("/invoices/{invoice_id}/online")
async def update_invoice_online_payment(
    invoice_id: int,
    data: OnlinePaymentUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        invoice = await PaymentService.set_online_payment_enabled(
            session, invoice_id, data.enabled, rotate_token=data.rotate_token
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "enabled": bool(invoice.online_payment_enabled),
        "payment_link_configured": bool(invoice.payment_token),
        "payment_url": (
            f"{settings.app_base_url.rstrip('/')}/pay/{invoice.payment_token}"
            if invoice.online_payment_enabled and invoice.payment_token
            else None
        ),
    }


async def _invoice_for_payment_token(session: AsyncSession, token: str) -> Invoice:
    invoice = (
        await session.execute(
            select(Invoice).where(
                Invoice.payment_token == token,
                Invoice.online_payment_enabled == 1,
                Invoice.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Payment link is invalid or disabled")
    return invoice


def _checkout_fingerprint(
    invoice: Invoice,
    *,
    token: str,
    provider_name: str,
    amount: Decimal,
    base_url: str,
) -> str:
    values = (
        provider_name,
        str(amount),
        invoice.currency_code.upper(),
        invoice.invoice_number,
        invoice.client_email or "",
        token,
        base_url,
    )
    return hashlib.sha256("\0".join(values).encode()).hexdigest()


@public_router.get("/pay/{token}")
@limiter.limit("20/minute")
async def begin_public_payment(
    request: Request,
    token: str,
    session: AsyncSession = Depends(get_session),
):
    invoice = await _invoice_for_payment_token(session, token)
    profile = await BusinessProfile.get_or_create(session)
    if not profile.online_payments_enabled:
        raise HTTPException(status_code=404, detail="Payment link is disabled")
    if invoice.document_type != "invoice" or invoice.status not in {
        "sent", "overdue", "partially_paid"
    }:
        raise HTTPException(status_code=409, detail="This invoice is not eligible for online payment")

    summary = await PaymentService.payment_summary(session, invoice)
    if summary["outstanding"] <= 0:
        raise HTTPException(status_code=409, detail="This invoice has already been paid")
    if summary["pending"] > 0:
        raise HTTPException(
            status_code=409,
            detail="A payment for this invoice is still processing",
        )
    try:
        amount_minor = to_minor_units(summary["outstanding"], invoice.currency_code)
        provider = get_payment_provider(profile)
        base_url = settings.app_base_url.rstrip("/")
        fingerprint = _checkout_fingerprint(
            invoice,
            token=token,
            provider_name=provider.name,
            amount=summary["outstanding"],
            base_url=base_url,
        )
        now = utc_now()
        fallback_expiry = now + timedelta(hours=24)
        active_expiry = ensure_utc(invoice.payment_checkout_expires_at)
        active_matches = bool(
            invoice.payment_checkout_idempotency_key
            and invoice.payment_checkout_provider == provider.name
            and quantize_money(invoice.payment_checkout_amount or 0)
            == summary["outstanding"]
            and invoice.payment_checkout_currency == invoice.currency_code.upper()
            and invoice.payment_checkout_fingerprint == fingerprint
            and active_expiry
            and active_expiry > now
        )
        if not active_matches:
            if invoice.payment_checkout_idempotency_key:
                await PaymentService.expire_active_checkout(session, invoice)
            claim_key = secrets.token_urlsafe(32)
            await session.execute(
                update(Invoice)
                .where(
                    Invoice.id == invoice.id,
                    or_(
                        Invoice.payment_checkout_idempotency_key.is_(None),
                        Invoice.payment_checkout_expires_at.is_(None),
                        Invoice.payment_checkout_expires_at <= now,
                        Invoice.payment_checkout_provider != provider.name,
                        Invoice.payment_checkout_amount != summary["outstanding"],
                        Invoice.payment_checkout_currency != invoice.currency_code.upper(),
                        Invoice.payment_checkout_fingerprint != fingerprint,
                    ),
                )
                .values(
                    payment_checkout_provider=provider.name,
                    payment_checkout_id=None,
                    payment_checkout_url=None,
                    payment_checkout_amount=summary["outstanding"],
                    payment_checkout_currency=invoice.currency_code.upper(),
                    payment_checkout_idempotency_key=claim_key,
                    payment_checkout_fingerprint=fingerprint,
                    payment_checkout_expires_at=fallback_expiry,
                )
            )
            await session.commit()
            await session.refresh(invoice)

        checkout_key = invoice.payment_checkout_idempotency_key
        if not checkout_key:
            raise PaymentProviderError("Checkout session could not be claimed")
        if invoice.payment_checkout_url:
            return RedirectResponse(invoice.payment_checkout_url, status_code=303)

        checkout = await provider.create_checkout(
            CheckoutRequest(
                invoice_id=invoice.id,
                invoice_number=invoice.invoice_number,
                amount_minor=amount_minor,
                currency_code=invoice.currency_code,
                customer_email=invoice.client_email,
                success_url=(
                    f"{base_url}/pay/{token}/success?session_id={{CHECKOUT_SESSION_ID}}"
                ),
                cancel_url=f"{base_url}/pay/{token}/cancelled",
                metadata={
                    "invoice_id": str(invoice.id),
                    "expected_amount_minor": str(amount_minor),
                    "currency_code": invoice.currency_code.upper(),
                },
                idempotency_key=checkout_key,
            )
        )
        await session.execute(
            update(Invoice)
            .where(
                Invoice.id == invoice.id,
                Invoice.payment_checkout_idempotency_key == checkout_key,
            )
            .values(
                payment_checkout_id=checkout.id,
                payment_checkout_url=checkout.url,
                payment_checkout_expires_at=checkout.expires_at or fallback_expiry,
            )
        )
        await session.commit()
    except (PaymentProviderError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RedirectResponse(checkout.url, status_code=303)


def _payment_page(title: str, message: str) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title>"
        "<body style='font:16px system-ui;max-width:38rem;margin:12vh auto;padding:2rem'>"
        f"<h1>{html.escape(title)}</h1><p>{html.escape(message)}</p></body></html>"
    )


@public_router.get("/pay/{token}/success")
async def public_payment_success(
    token: str, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    invoice = await _invoice_for_payment_token(session, token)
    summary = await PaymentService.payment_summary(session, invoice)
    if summary["outstanding"] == 0:
        return _payment_page("Payment received", "Thank you. This invoice is paid in full.")
    return _payment_page(
        "Payment processing",
        "Your payment is being confirmed. The invoice will update automatically.",
    )


@public_router.get("/pay/{token}/cancelled")
async def public_payment_cancelled(
    token: str, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    await _invoice_for_payment_token(session, token)
    return _payment_page("Payment cancelled", "No payment was recorded. You may close this page.")


@public_router.post("/api/payments/stripe/webhook")
async def stripe_webhook(
    request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    profile = await BusinessProfile.get_or_create(session)
    signature = request.headers.get("Stripe-Signature", "")
    payload = await request.body()
    try:
        provider = get_stripe_webhook_provider(profile)
        event = await provider.verify_event(payload, signature)
        return await PaymentService.process_provider_event(
            session, "stripe", event, hashlib.sha256(payload).hexdigest()
        )
    except PaymentProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
