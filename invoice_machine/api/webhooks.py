"""Inbound provider webhooks.

These endpoints are intentionally unauthenticated in the app's own terms —
Stripe cannot present a session cookie or a bot API key — so authenticity rests
entirely on the provider's request signature. Nothing here trusts the request
body until that signature verifies.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import BusinessProfile, Invoice, get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.services import PaymentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Refuse oversized bodies before hashing them.
MAX_WEBHOOK_BODY_BYTES = 512 * 1024


@router.post("/stripe")
@limiter.limit("120/minute")
async def stripe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Record payments completed through a Stripe Checkout Session.

    Always returns 2xx for events that verify but that this app does not act on —
    a non-2xx tells Stripe to retry, and retrying an event we intend to ignore
    accomplishes nothing.
    """
    from invoice_machine.service.stripe_links import (
        extract_payment_from_event,
        get_stripe_webhook_secret,
        verify_webhook_signature,
    )

    profile = await BusinessProfile.get(session)
    if not profile or not profile.payments_enabled:
        raise HTTPException(status_code=404, detail="Payments are not enabled")

    webhook_secret = get_stripe_webhook_secret(profile)
    if not webhook_secret:
        logger.error("Stripe webhook received but no signing secret is configured")
        raise HTTPException(status_code=503, detail="Webhook signing secret is not configured")

    raw_body = await request.body()
    if len(raw_body) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Webhook payload too large")

    try:
        event = verify_webhook_signature(
            raw_body, request.headers.get("Stripe-Signature"), webhook_secret
        )
    except ValueError as exc:
        # Deliberately terse: a detailed reason helps an attacker probe the
        # verification logic. The real reason is logged server-side.
        logger.warning("Rejected Stripe webhook: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid signature")

    details = extract_payment_from_event(event)
    if details is None:
        return {"received": True, "handled": False, "reason": "event not actionable"}

    # Idempotency: Stripe retries until it gets a 2xx, so the same event id can
    # arrive several times. The unique (provider, external_id) index and this
    # pre-check together ensure one event records at most one payment.
    existing = await PaymentService.find_by_external_id(session, "stripe", details["external_id"])
    if existing is not None:
        return {"received": True, "handled": True, "duplicate": True}

    invoice = await session.get(Invoice, details["invoice_id"])
    if invoice is not None and (invoice.currency_code or "").upper() != details["currency_code"]:
        logger.error(
            "Stripe session for invoice %s paid in %s, invoice is in %s; not recorded",
            invoice.id,
            details["currency_code"],
            invoice.currency_code,
        )
        return {"received": True, "handled": False, "reason": "currency mismatch"}

    try:
        payment = await PaymentService.record_payment(
            session,
            details["invoice_id"],
            amount=details["amount"],
            payment_date=details["payment_date"],
            method="stripe",
            reference=details.get("session_id"),
            provider="stripe",
            external_id=details["external_id"],
            # The customer really did pay this; never reject it for exceeding the
            # balance (e.g. the invoice was edited after the link was sent).
            allow_overpayment=True,
        )
    except ValueError as exc:
        await session.rollback()
        # 200 on purpose: the money moved and a retry would fail identically.
        # Surfacing it in the log is the actionable outcome.
        logger.error(
            "Stripe payment for invoice %s could not be recorded: %s",
            details["invoice_id"],
            exc,
        )
        return {"received": True, "handled": False, "reason": "could not record payment"}

    if payment is None:
        logger.error(
            "Stripe payment received for unknown invoice %s (event %s)",
            details["invoice_id"],
            details["external_id"],
        )
        return {"received": True, "handled": False, "reason": "invoice not found"}

    logger.info(
        "Recorded Stripe payment of %s for invoice %s",
        details["amount"],
        details["invoice_id"],
    )
    return {"received": True, "handled": True, "payment_id": payment.id}
