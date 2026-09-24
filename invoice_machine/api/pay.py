"""The public pay page behind every shared payment link.

No login: the unguessable token in the path is the credential, and it only
ever starts a Stripe checkout for that invoice's outstanding balance.
"""

import logging
from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.config import get_settings
from invoice_machine.database import BusinessProfile, Invoice, get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.service.common import format_currency
from invoice_machine.service.stripe_links import StripeError, create_payment_link

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title}</title>
<style>
body{{font-family:system-ui,sans-serif;background:#f5f5f4;color:#1c1917;margin:0;
display:grid;place-items:center;min-height:100vh}}
main{{background:#fff;border-radius:12px;padding:2rem;max-width:26rem;margin:1rem;
box-shadow:0 1px 3px rgba(0,0,0,.1)}}
h1{{font-size:1.25rem;margin:0 0 .75rem}}p{{line-height:1.5;margin:0 0 1rem}}
a.button{{display:inline-block;background:#16a34a;color:#fff;padding:.6rem 1.2rem;
border-radius:8px;text-decoration:none;font-weight:600}}
</style></head>
<body><main><h1>{title}</h1>{body}</main></body></html>"""


def _page(title: str, message: str, *, action: str = "", status_code: int = 200) -> HTMLResponse:
    body = f"<p>{escape(message)}</p>{action}"
    return HTMLResponse(_PAGE.format(title=escape(title), body=body), status_code=status_code)


@router.get("/pay/{token}")
@limiter.limit("30/minute")
async def pay_invoice(
    request: Request,
    token: str,
    result: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Send the client to a fresh Stripe checkout for what is still owed."""
    invoice = None
    if token:
        invoice = (
            await session.execute(
                select(Invoice).where(
                    Invoice.payment_link_id == token,
                    Invoice.deleted_at.is_(None),
                    Invoice.document_type == "invoice",
                )
            )
        ).scalar_one_or_none()
    if invoice is None:
        return _page(
            "Payment link not found",
            "This payment link is not valid. Please contact the sender of the invoice.",
            status_code=404,
        )

    profile = await BusinessProfile.get_or_create(session)
    sender = profile.business_name or profile.name or "the sender"
    title = f"Invoice {invoice.invoice_number}"

    if result == "paid":
        return _page(title, f"Thank you. Your payment to {sender} was received.")
    if invoice.status == "cancelled":
        return _page(title, f"This invoice was cancelled. Please contact {sender}.")
    if invoice.amount_due <= 0:
        return _page(title, "This invoice is paid in full. Thank you.")

    due = format_currency(invoice.amount_due, invoice.currency_code)
    if result == "cancelled":
        # A plain link back here, not an automatic redirect: the client chose to leave.
        return _page(
            title,
            f"Payment was cancelled. {due} is still due.",
            action=f'<a class="button" href="{escape(request.url.path)}">Pay {escape(due)}</a>',
        )

    base_url = profile.app_base_url or get_settings().app_base_url or ""
    if not profile.payments_enabled or not base_url:
        return _page(title, f"Online payment is not available. Please contact {sender}.")
    try:
        link = await create_payment_link(profile, invoice, base_url)
    except StripeError:
        logger.warning("Pay page could not start a checkout for invoice %s", invoice.id)
        return _page(
            title,
            f"Online payment is unavailable right now. Please try again later or contact {sender}.",
            status_code=503,
        )
    return RedirectResponse(link["url"], status_code=303)
