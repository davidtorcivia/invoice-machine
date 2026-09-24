"""PDF generator using WeasyPrint."""

import base64
import os
import tempfile
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from weasyprint import HTML
from weasyprint.urls import URLFetcher

from invoice_machine.config import get_settings
from invoice_machine.database import BusinessProfile, Invoice, InvoiceItem
from invoice_machine.service.common import format_currency, format_quantity
from invoice_machine.utils import (
    confined_file,
    detect_image_type,
    sanitize_filename_component,
    utc_now,
)

settings = get_settings()

template_dir = Path(__file__).parent
env = Environment(
    loader=FileSystemLoader(template_dir),
    autoescape=select_autoescape(["html"]),
)


def strftime_filter(date_obj, format_str="%m/%d/%y"):
    """Format a date object as a string."""
    if date_obj is None:
        return ""
    if hasattr(date_obj, "strftime"):
        return date_obj.strftime(format_str)
    return str(date_obj)


def zfill_filter(value, width):
    """Pad a value with zeros to the specified width."""
    return str(value).zfill(width)


env.filters["strftime"] = strftime_filter
env.filters["zfill"] = zfill_filter
env.filters["format_quantity"] = format_quantity


def invoice_pdf_filename(invoice: Invoice) -> str:
    """Build the on-disk PDF filename for an invoice.

    The invoice id is part of the name because ``sanitize_filename_component``
    drops dots and other punctuation: "INV.001" and "INV001" are distinct,
    unique invoice numbers that both sanitize to "INV001", so a number-only
    filename let one invoice's PDF be served (and emailed) for another.
    The user-facing download name is built separately from the raw number.
    """
    safe_invoice_number = sanitize_filename_component(
        invoice.invoice_number, f"invoice-{invoice.id}"
    )
    return f"{safe_invoice_number}-{invoice.id}.pdf"


def _generate_pdf_sync(html: str, pdf_path: Path) -> None:
    """Render the PDF synchronously; call it off the event loop.

    The render goes to a temp file in the same directory and is then moved into
    place with os.replace, so a concurrent reader (or a render that fails
    halfway) can never observe a truncated PDF at the destination path.
    """
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(suffix=".pdf.tmp", dir=pdf_path.parent)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        # Only inline data: URIs (the logo). Refusing file: and http: stops CSS or
        # HTML injection from reading local files or reaching internal hosts.
        fetcher = URLFetcher(allowed_protocols={"data"})
        HTML(string=html, url_fetcher=fetcher).write_pdf(tmp_path)
        os.replace(tmp_path, pdf_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _read_logo_bytes(business: BusinessProfile) -> bytes | None:
    """Read the configured logo, refusing anything outside the logo directory."""
    if not business.logo_path:
        return None

    logo_file = confined_file(settings.logo_dir, business.logo_path)
    if logo_file is None or not logo_file.is_file():
        return None

    return logo_file.read_bytes()


def get_logo_data_uri(business: BusinessProfile) -> str | None:
    """Get the logo as a complete ``data:`` URI with a content-derived MIME type."""
    data = _read_logo_bytes(business)
    if data is None:
        return None
    # MIME from the bytes: the stored filename extension is attacker-influenced.
    detected = detect_image_type(data)
    mime = detected[1] if detected else "application/octet-stream"
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _payment_instructions(invoice: Invoice, business: BusinessProfile) -> tuple[str | None, bool]:
    """Resolve the invoice's payment instructions and whether to print them.

    The chosen payment methods win; the business default fills in only when the
    invoice asks for instructions and no chosen method supplied any.
    """
    show_payment_instructions = bool(getattr(invoice, "show_payment_instructions", True))
    payment_instructions = None
    selected_payment_methods = getattr(invoice, "selected_payment_methods_list", [])

    if selected_payment_methods:
        available_methods = getattr(business, "payment_methods_list", [])

        if available_methods:
            selected_methods_list = []
            for method in available_methods:
                if method.get("id") in selected_payment_methods:
                    selected_methods_list.append(method)

            if selected_methods_list:
                if len(selected_methods_list) == 1:
                    method = selected_methods_list[0]
                    payment_instructions = method.get("instructions", "")
                else:
                    instructions_parts = []
                    for method in selected_methods_list:
                        name = method.get("name", "")
                        instructions = method.get("instructions", "")
                        if name and instructions:
                            instructions_parts.append(f"{name}:\n{instructions}")
                        elif instructions:
                            instructions_parts.append(instructions)
                    payment_instructions = "\n\n".join(instructions_parts)

    if show_payment_instructions and not payment_instructions:
        payment_instructions = getattr(business, "default_payment_instructions", None)

    show_payment_section = bool(
        payment_instructions and (selected_payment_methods or show_payment_instructions)
    )
    return payment_instructions, show_payment_section


async def generate_pdf(session: AsyncSession, invoice: Invoice) -> str:
    """Render the invoice PDF and return its path relative to the data directory."""
    business = await BusinessProfile.get_or_create(session)

    from sqlalchemy import select

    result = await session.execute(
        select(InvoiceItem)
        .where(InvoiceItem.invoice_id == invoice.id)
        .order_by(InvoiceItem.sort_order)
    )
    items = result.scalars().all()

    has_hours = any(getattr(item, "unit_type", "qty") == "hours" for item in items)

    payment_instructions, show_payment_section = _payment_instructions(invoice, business)

    template = env.get_template("template.html")

    logo_data_uri = await run_in_threadpool(get_logo_data_uri, business)

    html = template.render(
        business=business,
        invoice=invoice,
        items=items,
        logo_data_uri=logo_data_uri,
        format_money=format_currency,
        has_hours=has_hours,
        show_payment_instructions=show_payment_section,
        payment_instructions=payment_instructions,
        # A quote is not a bill: never invite payment or show a balance on one.
        payment_link_url=(invoice.payment_link_url if invoice.document_type != "quote" else None),
        amount_paid=invoice.amount_paid or Decimal("0.00"),
        amount_due=invoice.amount_due,
    )

    pdf_filename = invoice_pdf_filename(invoice)
    pdf_path = settings.pdf_dir / pdf_filename

    await run_in_threadpool(_generate_pdf_sync, html, pdf_path)

    return f"pdfs/{pdf_filename}"


def _stored_pdf_exists(pdf_path: str) -> bool:
    """Backups exclude pdfs/, so a fresh stamp can point at a file that is gone."""
    candidate = confined_file(settings.pdf_dir, Path(pdf_path).name)
    return candidate is not None and candidate.is_file()


async def store_invoice_pdf(session: AsyncSession, invoice: Invoice, *, force: bool = False) -> str:
    """Render the invoice PDF when it is missing or stale and persist the stamp.

    Every caller (REST, MCP, the email flow) must go through this so the
    freshness bookkeeping stays consistent.

    ``updated_at`` is pinned to its current value via an explicit Core UPDATE.
    The column's ``onupdate`` default would otherwise stamp it at flush time —
    always a hair *later* than the ``pdf_generated_at`` written in the same
    statement — leaving the invoice permanently "stale" and re-rendering the PDF
    on every single fetch.
    """
    if (
        not force
        and invoice.pdf_path
        and not invoice.needs_pdf_regeneration
        and _stored_pdf_exists(invoice.pdf_path)
    ):
        return invoice.pdf_path

    pdf_path = await generate_pdf(session, invoice)
    generated_at = utc_now()
    await session.execute(
        update(Invoice)
        .where(Invoice.id == invoice.id)
        .values(
            pdf_path=pdf_path,
            pdf_generated_at=generated_at,
            updated_at=invoice.updated_at,
        )
    )
    await session.commit()

    invoice.pdf_path = pdf_path
    invoice.pdf_generated_at = generated_at
    return pdf_path
