"""PDF generator using WeasyPrint."""

import base64
import json
from pathlib import Path
from decimal import Decimal
from typing import Optional, Union

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from weasyprint import HTML, CSS

from invoice_machine.database import Invoice, InvoiceItem, BusinessProfile
from invoice_machine.config import get_settings

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

env.filters["strftime"] = strftime_filter
env.filters["zfill"] = zfill_filter


def format_money(amount: Union[Decimal, str, float], currency_code: str = "USD") -> str:
    """Format amount as currency string."""
    amount = Decimal(str(amount))
    if currency_code == "USD":
        return f"${amount:,.2f}"
    return f"{amount:,.2f} {currency_code}"


def _generate_pdf_sync(html: str, pdf_path: Path) -> None:
    """
    Synchronous PDF generation using WeasyPrint.

    This is called in a thread pool to avoid blocking the async event loop.
    """
    HTML(string=html).write_pdf(pdf_path)


def get_logo_base64(business: BusinessProfile) -> Optional[str]:
    """Get logo as base64 data URL."""
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

    data = logo_file.read_bytes()
    return base64.b64encode(data).decode("ascii")


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
    selected_payment_methods = []

    # Try to get selected payment methods from invoice
    selected_methods_json = getattr(invoice, "selected_payment_methods", None)
    if selected_methods_json:
        try:
            selected_payment_methods = json.loads(selected_methods_json)
        except (json.JSONDecodeError, TypeError):
            pass

    # Build payment instructions from selected methods
    if selected_payment_methods:
        # Parse available payment methods from business profile
        available_methods = []
        methods_json = getattr(business, "payment_methods", None)
        if methods_json:
            try:
                available_methods = json.loads(methods_json)
            except (json.JSONDecodeError, TypeError):
                pass

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

    # Get logo data
    logo_data = get_logo_base64(business)

    # Determine if we should show payment section
    # Show if we have payment instructions (from selected methods or default)
    show_payment_section = bool(payment_instructions and (selected_payment_methods or show_payment_instructions))

    # Render HTML
    html = template.render(
        business=business,
        invoice=invoice,
        items=items,
        logo_data=logo_data,
        format_money=format_money,
        has_hours=has_hours,
        show_payment_instructions=show_payment_section,
        payment_instructions=payment_instructions,
    )

    # Generate PDF filename
    pdf_filename = f"{invoice.invoice_number}.pdf"
    pdf_path = settings.pdf_dir / pdf_filename

    # Generate PDF using WeasyPrint in a thread pool to avoid blocking
    await run_in_threadpool(_generate_pdf_sync, html, pdf_path)

    # Return relative path for storage
    return f"pdfs/{pdf_filename}"
