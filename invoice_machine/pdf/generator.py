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

from invoice_machine.config import get_settings
from invoice_machine.database import BusinessProfile, Invoice, InvoiceItem
from invoice_machine.utils import sanitize_filename_component, utc_now

settings = get_settings()

# Set up Jinja2 environment
template_dir = Path(__file__).parent
env = Environment(
    loader=FileSystemLoader(template_dir),
    autoescape=select_autoescape(["html"]),
)

# Register custom filters
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

def quantity_filter(value):
    """Render a quantity without trailing zeros (2, 1.5, 0.25)."""
    from invoice_machine.service.common import format_quantity

    return format_quantity(value)

env.filters["strftime"] = strftime_filter
env.filters["zfill"] = zfill_filter
env.filters["format_quantity"] = quantity_filter


def format_money(amount: Decimal | str | float, currency_code: str = "USD") -> str:
    """Format amount as currency string."""
    from invoice_machine.service.common import format_currency

    return format_currency(amount, currency_code)


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


def _pdf_url_fetcher(url: str):
    """Restrict WeasyPrint to inline ``data:`` URIs during rendering.

    The template embeds the logo as a base64 ``data:`` URI and needs no network or
    filesystem access. Refusing everything else neutralizes any CSS/HTML injection
    (e.g. a crafted ``accent_color``) that tries ``url(file://...)`` or
    ``url(http://...)`` to read local files or reach internal services (SSRF).
    """
    if url.startswith("data:"):
        from weasyprint.urls import default_url_fetcher

        return default_url_fetcher(url)
    raise ValueError(f"Blocked non-data resource during PDF render: {url[:64]}")


def _generate_pdf_sync(html: str, pdf_path: Path) -> None:
    """
    Synchronous PDF generation using WeasyPrint.

    This is called in a thread pool to avoid blocking the async event loop.
    The render goes to a temp file in the same directory and is then moved into
    place with os.replace, so a concurrent reader (or a render that fails
    halfway) can never observe a truncated PDF at the destination path.
    """
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(suffix=".pdf.tmp", dir=pdf_path.parent)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        HTML(string=html, url_fetcher=_pdf_url_fetcher).write_pdf(tmp_path)
        os.replace(tmp_path, pdf_path)
    finally:
        tmp_path.unlink(missing_ok=True)


# Magic-byte -> MIME map for the logo data: URI. The stored filename extension is
# attacker-influenced (and the upload validator only checks content), so the MIME
# type is derived from the bytes instead of hardcoded to image/png.
_LOGO_MIME_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def _logo_mime_type(data: bytes) -> str:
    """Detect the logo's MIME type from its magic bytes."""
    for signature, mime in _LOGO_MIME_SIGNATURES:
        if data.startswith(signature):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _read_logo_bytes(business: BusinessProfile) -> bytes | None:
    """Read the configured logo, refusing anything outside the logo directory."""
    if not business.logo_path:
        return None

    # Validate logo path to prevent path traversal
    logo_path = business.logo_path

    # Reject any path separators or parent directory references
    if "/" in logo_path or "\\" in logo_path or ".." in logo_path:
        return None

    logo_file = settings.logo_dir / logo_path

    # Verify resolved path is within logo_dir
    try:
        resolved = logo_file.resolve()
        logo_dir_resolved = settings.logo_dir.resolve()
        if not str(resolved).startswith(str(logo_dir_resolved)):
            return None
    except (OSError, ValueError):
        return None

    if not logo_file.exists():
        return None

    return logo_file.read_bytes()


def get_logo_base64(business: BusinessProfile) -> str | None:
    """Get logo as a base64 string."""
    data = _read_logo_bytes(business)
    if data is None:
        return None
    return base64.b64encode(data).decode("ascii")


def get_logo_data_uri(business: BusinessProfile) -> str | None:
    """Get the logo as a complete ``data:`` URI with a content-derived MIME type.

    The template previously hardcoded ``image/png`` for every logo, even though
    JPEG/GIF/WebP uploads are allowed.
    """
    data = _read_logo_bytes(business)
    if data is None:
        return None
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{_logo_mime_type(data)};base64,{encoded}"


async def generate_pdf(session: AsyncSession, invoice: Invoice) -> str:
    """
    Generate PDF for an invoice.

    Returns the relative path to the generated PDF file.
    """
    # Get business profile
    business = await BusinessProfile.get_or_create(session)

    # Get invoice items (sorted)
    from sqlalchemy import select

    result = await session.execute(
        select(InvoiceItem)
        .where(InvoiceItem.invoice_id == invoice.id)
        .order_by(InvoiceItem.sort_order)
    )
    items = result.scalars().all()

    # Determine if any items use hours
    has_hours = any(getattr(item, "unit_type", "qty") == "hours" for item in items)

    # Get payment instructions from selected payment methods
    show_payment_instructions = bool(getattr(invoice, "show_payment_instructions", True))
    payment_instructions = None
    selected_payment_methods = getattr(invoice, "selected_payment_methods_list", [])

    # Build payment instructions from selected methods
    if selected_payment_methods:
        # Parse available payment methods from business profile
        available_methods = getattr(business, "payment_methods_list", [])

        # Filter to selected methods and build instructions
        if available_methods:
            selected_methods_list = []
            for method in available_methods:
                if method.get("id") in selected_payment_methods:
                    selected_methods_list.append(method)

            if selected_methods_list:
                if len(selected_methods_list) == 1:
                    # Single method - just show instructions
                    method = selected_methods_list[0]
                    payment_instructions = method.get("instructions", "")
                else:
                    # Multiple methods - show name and instructions for each
                    instructions_parts = []
                    for method in selected_methods_list:
                        name = method.get("name", "")
                        instructions = method.get("instructions", "")
                        if name and instructions:
                            instructions_parts.append(f"{name}:\n{instructions}")
                        elif instructions:
                            instructions_parts.append(instructions)
                    payment_instructions = "\n\n".join(instructions_parts)

    # Fall back to default payment instructions if no methods selected but show is enabled
    if show_payment_instructions and not payment_instructions:
        payment_instructions = getattr(business, "default_payment_instructions", None)

    # Load template
    template = env.get_template("template.html")

    # Get logo as a self-describing data: URI (MIME type derived from content)
    logo_data_uri = get_logo_data_uri(business)

    # Determine if we should show payment section
    # Show if we have payment instructions (from selected methods or default)
    show_payment_section = bool(payment_instructions and (selected_payment_methods or show_payment_instructions))

    # Render HTML
    html = template.render(
        business=business,
        invoice=invoice,
        items=items,
        logo_data_uri=logo_data_uri,
        format_money=format_money,
        has_hours=has_hours,
        show_payment_instructions=show_payment_section,
        payment_instructions=payment_instructions,
        # A quote is not a bill: never invite payment or show a balance on one.
        payment_link_url=(
            invoice.payment_link_url if invoice.document_type != "quote" else None
        ),
        amount_paid=invoice.amount_paid or Decimal("0.00"),
        amount_due=invoice.amount_due,
    )

    pdf_filename = invoice_pdf_filename(invoice)
    pdf_path = settings.pdf_dir / pdf_filename

    # Generate PDF using WeasyPrint in a thread pool to avoid blocking
    await run_in_threadpool(_generate_pdf_sync, html, pdf_path)

    # Return relative path for storage
    return f"pdfs/{pdf_filename}"


async def store_invoice_pdf(
    session: AsyncSession, invoice: Invoice, *, force: bool = False
) -> str:
    """Render the invoice PDF when it is missing or stale and persist the stamp.

    Every caller (REST, MCP, the email flow) must go through this so the
    freshness bookkeeping stays consistent.

    ``updated_at`` is pinned to its current value via an explicit Core UPDATE.
    The column's ``onupdate`` default would otherwise stamp it at flush time —
    always a hair *later* than the ``pdf_generated_at`` written in the same
    statement — leaving the invoice permanently "stale" and re-rendering the PDF
    on every single fetch.
    """
    if not force and invoice.pdf_path and not invoice.needs_pdf_regeneration:
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
