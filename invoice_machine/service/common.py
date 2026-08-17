"""Shared service-layer helpers."""

import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import BusinessProfile, Client, Invoice, InvoiceItem

# Matches auto-generated numbers like "20260115-1" or "Q-20260115-3".
_AUTO_INVOICE_NUMBER_RE = re.compile(r"^(Q-)?\d{8}-\d+$")


def is_auto_invoice_number(number: str | None) -> bool:
    """Return True if a number looks auto-generated (vs. a manual override)."""
    return bool(number) and _AUTO_INVOICE_NUMBER_RE.fullmatch(number) is not None


# All monetary values are rounded to 2 decimal places. SQLite does not enforce
# DECIMAL(10,2) scale, so quantization must happen in Python before persisting.
CENTS = Decimal("0.01")

# Statuses that count as actually billed. Excludes "draft" (not yet issued) and
# "cancelled" (voided) so neither inflates invoiced/revenue/LTV totals. Shared by
# the REST analytics service and the MCP client-context tool so they agree.
BILLED_STATUSES = ("sent", "paid", "overdue")


def quantize_money(amount: Decimal | float | int | str) -> Decimal:
    """Round a monetary amount to 2 decimal places (ROUND_HALF_UP)."""
    return Decimal(str(amount)).quantize(CENTS, rounding=ROUND_HALF_UP)


def line_item_total(
    unit_price: Decimal | float | int | str, quantity: Decimal | float | int | str
) -> Decimal:
    """Compute a line-item total, quantized to cents."""
    return quantize_money(Decimal(str(unit_price)) * Decimal(str(quantity)))


# Quantities support up to 3 decimal places (e.g. 1.5 hours, 0.25 hours).
QUANTITY_PRECISION = Decimal("0.001")


def quantize_quantity(value: Decimal | float | int | str) -> Decimal:
    """Coerce a line-item quantity to a positive Decimal (max 3dp)."""
    try:
        qty = Decimal(str(value)).quantize(QUANTITY_PRECISION, rounding=ROUND_HALF_UP)
    except (ArithmeticError, ValueError, TypeError):
        raise ValueError("Quantity must be a number") from None
    if qty <= 0:
        raise ValueError("Quantity must be greater than 0")
    return qty


def format_quantity(value: Decimal | float | int | str) -> str:
    """Render a quantity without trailing zeros ("2", "1.5", "0.25")."""
    text = f"{Decimal(str(value)):.3f}".rstrip("0").rstrip(".")
    return text or "0"


VALID_UNIT_TYPES = {"qty", "hours"}


def normalize_line_items(items: list[dict] | None) -> list[dict]:
    """Validate and normalize raw line-item dicts.

    Coerces quantity/unit_price (tolerant of str/float from MCP or stored JSON),
    rejects negative prices and unknown unit types, and computes the quantized
    line total. Used by both invoice creation and recurring-schedule saves so a
    bad item fails fast at the API boundary instead of poisoning later generation.
    """
    normalized: list[dict] = []
    for index, item_data in enumerate(items or []):
        quantity = quantize_quantity(item_data.get("quantity", 1))
        raw_price = item_data.get("unit_price", 0)
        try:
            unit_price = Decimal(str(raw_price))
        except (ArithmeticError, ValueError, TypeError):
            raise ValueError("Unit price must be a number") from None
        if not unit_price.is_finite():
            raise ValueError("Unit price must be a finite number")
        if unit_price < 0:
            raise ValueError("Unit price cannot be negative")
        unit_type = item_data.get("unit_type", "qty")
        if unit_type not in VALID_UNIT_TYPES:
            raise ValueError(f"Invalid unit type. Must be one of: {sorted(VALID_UNIT_TYPES)}")
        normalized.append(
            {
                "description": item_data.get("description", ""),
                "quantity": quantity,
                "unit_type": unit_type,
                "unit_price": unit_price,
                "total": line_item_total(unit_price, quantity),
                "sort_order": item_data.get("sort_order", index),
            }
        )
    return normalized


async def generate_invoice_number(
    session: AsyncSession, issue_date: date, document_type: str = "invoice"
) -> str:
    """Generate an invoice or quote number for a specific issue date."""
    date_prefix = issue_date.strftime("%Y%m%d")
    prefix = "Q-" if document_type == "quote" else ""
    search_prefix = f"{prefix}{date_prefix}"

    result = await session.execute(
        select(Invoice.invoice_number).where(Invoice.invoice_number.like(f"{search_prefix}-%"))
    )
    existing_numbers = result.scalars().all()

    max_seq = 0
    for num in existing_numbers:
        try:
            parts = num[2:].split("-") if num.startswith("Q-") else num.split("-")
            if len(parts) == 2 and parts[0] == date_prefix:
                max_seq = max(max_seq, int(parts[1]))
        except (ValueError, IndexError):
            continue

    return f"{prefix}{date_prefix}-{max_seq + 1}"


def calculate_due_date(
    issue_date: date,
    payment_terms_days: int | None = None,
    explicit_due_date: date | None = None,
    client: Client | None = None,
    business: BusinessProfile | None = None,
) -> date:
    """Calculate invoice due date using invoice, client, business, then default terms."""
    if explicit_due_date:
        return explicit_due_date

    terms = (
        payment_terms_days
        or (client.payment_terms_days if client else None)
        or (business.default_payment_terms_days if business else None)
        or 30
    )
    return issue_date + timedelta(days=terms)


async def recalculate_invoice_totals(session: AsyncSession, invoice: Invoice):
    """Recalculate subtotal, tax, and total from current line items."""
    result = await session.execute(
        select(InvoiceItem.total).where(InvoiceItem.invoice_id == invoice.id)
    )
    item_totals = result.scalars().all()

    subtotal = quantize_money(sum((Decimal(str(total)) for total in item_totals), Decimal("0")))
    invoice.subtotal = subtotal

    if invoice.tax_enabled and invoice.tax_rate and invoice.tax_rate > 0:
        invoice.tax_amount = quantize_money(subtotal * invoice.tax_rate / Decimal("100"))
    else:
        invoice.tax_amount = Decimal("0.00")

    invoice.total = quantize_money(subtotal + invoice.tax_amount)


async def snapshot_client_info(session: AsyncSession, client: Client, invoice: Invoice):
    """Copy client details onto an invoice so the document remains historically stable."""
    del session
    invoice.client_name = client.name
    invoice.client_business = client.business_name
    invoice.client_email = client.email

    address_lines: list[str] = []
    street_parts = [part for part in [client.address_line1, client.address_line2] if part]
    if street_parts:
        address_lines.append(", ".join(street_parts))

    city_line_parts = []
    if client.city:
        city_line_parts.append(client.city)
    if client.state:
        city_line_parts.append(client.state)
    if city_line_parts:
        city_line = ", ".join(city_line_parts)
        if client.postal_code:
            city_line += f" {client.postal_code}"
        address_lines.append(city_line)
    elif client.postal_code:
        address_lines.append(client.postal_code)

    if client.country:
        address_lines.append(client.country)

    invoice.client_address = "\n".join(address_lines) if address_lines else None


def resolve_exchange_rate(
    business: BusinessProfile | None,
    currency_code: str,
    explicit_rate: Decimal | None = None,
) -> Decimal | None:
    """Resolve the rate converting ``currency_code`` into the business base currency.

    Precedence: an explicit per-invoice rate, then the profile's configured rate
    table, then 1 when the invoice already *is* in the base currency. Returns None
    when no rate is known — consolidated reporting then excludes the invoice and
    reports it as uncovered instead of inventing a rate.
    """
    if explicit_rate is not None:
        rate = Decimal(str(explicit_rate))
        if not rate.is_finite() or rate <= 0:
            raise ValueError("Exchange rate must be a positive number")
        return rate

    base = (business.default_currency_code if business else None) or "USD"
    code = (currency_code or base).upper()
    if code == base.upper():
        return Decimal("1")

    if business is not None:
        configured = business.fx_rates_map.get(code)
        if configured is not None:
            return configured

    return None


def convert_to_base(
    amount: Decimal | float | int | str, exchange_rate: Decimal | None
) -> Decimal | None:
    """Convert an amount into the base currency, or None when no rate is known."""
    if exchange_rate is None:
        return None
    return quantize_money(Decimal(str(amount)) * Decimal(str(exchange_rate)))


def format_currency(amount: Decimal | float | str, currency_code: str = "USD") -> str:
    """Format a money value for display."""
    amount = Decimal(str(amount))
    if currency_code == "USD":
        return f"${amount:,.2f}"
    return f"{amount:,.2f} {currency_code}"


def is_invoice_document(document: Invoice) -> bool:
    """Return True when a document should count toward billed totals."""
    return getattr(document, "document_type", "invoice") == "invoice"


VALID_RECURRING_FREQUENCIES = ("daily", "weekly", "monthly", "quarterly", "yearly")


def _replace_with_valid_day(target_date: date, schedule_day: int) -> date:
    """Clamp a schedule day to the last valid day in the target month."""
    from dateutil.relativedelta import relativedelta

    last_day = ((target_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)).day
    return target_date.replace(day=min(schedule_day, last_day))


def _align_to_quarter_month(target_date: date, quarter_month: int, schedule_day: int) -> date:
    """Move a date to the configured month within its calendar quarter.

    ``quarter_month`` is 1-3 (1st/2nd/3rd month of the quarter), so a quarterly
    schedule set to the "2nd month" always bills in Feb/May/Aug/Nov regardless of
    which month the schedule happened to be created in.
    """
    offset = min(max(int(quarter_month or 1), 1), 3) - 1
    quarter_start_month = ((target_date.month - 1) // 3) * 3 + 1
    aligned = target_date.replace(day=1, month=quarter_start_month + offset)
    return _replace_with_valid_day(aligned, schedule_day)


def _align_to_year_month(target_date: date, schedule_month: int | None, schedule_day: int) -> date:
    """Move a date to the configured calendar month for a yearly schedule."""
    if schedule_month is None:
        return _replace_with_valid_day(target_date, schedule_day)
    month = min(max(int(schedule_month), 1), 12)
    aligned = target_date.replace(day=1, month=month)
    return _replace_with_valid_day(aligned, schedule_day)


def validate_recurring_schedule(
    frequency: str,
    schedule_day: int,
    payment_terms_days: int | None = None,
    tax_rate: Decimal | None = None,
    schedule_month: int | None = None,
    quarter_month: int | None = None,
) -> None:
    """Validate recurring schedule cadence and financial fields."""
    if frequency not in VALID_RECURRING_FREQUENCIES:
        raise ValueError(f"Invalid frequency. Must be one of: {list(VALID_RECURRING_FREQUENCIES)}")

    if frequency == "weekly" and not (0 <= schedule_day <= 6):
        raise ValueError("For weekly frequency, schedule_day must be 0-6 (Monday-Sunday)")

    if frequency in {"monthly", "quarterly", "yearly"} and not (1 <= schedule_day <= 31):
        raise ValueError("For monthly/quarterly/yearly frequency, schedule_day must be 1-31")

    if schedule_month is not None and not (1 <= schedule_month <= 12):
        raise ValueError("schedule_month must be 1-12")

    if quarter_month is not None and not (1 <= quarter_month <= 3):
        raise ValueError("quarter_month must be 1-3 (which month within the quarter)")

    if payment_terms_days is not None and not (0 <= payment_terms_days <= 365):
        raise ValueError("Payment terms must be between 0 and 365 days")

    if tax_rate is not None and (tax_rate < 0 or tax_rate > 100):
        raise ValueError("Tax rate must be between 0 and 100")


def delete_invoice_pdf_files(pdf_paths: list[str]) -> int:
    """Best-effort removal of generated PDFs for permanently deleted invoices.

    Purging an invoice used to leave its rendered PDF behind forever, so the
    pdfs/ directory grew without bound and kept documents on disk for records the
    user had explicitly destroyed.
    """
    import logging
    import os

    from invoice_machine.config import get_settings
    from invoice_machine.utils import confined_file

    logger = logging.getLogger(__name__)
    pdf_dir = get_settings().pdf_dir

    removed = 0
    for stored_path in pdf_paths:
        if not stored_path:
            continue
        # Stored as "pdfs/<name>.pdf"; only ever touch that one directory.
        name = os.path.basename(stored_path)
        candidate = confined_file(pdf_dir, name)
        if candidate is None:
            continue
        try:
            if candidate.is_file():
                candidate.unlink()
                removed += 1
        except OSError as exc:
            logger.warning("Could not delete PDF %s: %s", name, exc)
    return removed


async def purge_trashed_records(
    session: AsyncSession,
    deleted_before: datetime | None = None,
) -> dict[str, int]:
    """Delete trashed invoices and only then delete unreferenced trashed clients.

    Also removes the generated PDF for each purged invoice.
    """
    invoice_conditions = [Invoice.deleted_at.is_not(None)]
    client_conditions = [Client.deleted_at.is_not(None)]
    if deleted_before is not None:
        invoice_conditions.append(Invoice.deleted_at < deleted_before)
        client_conditions.append(Client.deleted_at < deleted_before)

    invoice_filter = and_(*invoice_conditions)
    client_filter = and_(*client_conditions)
    remaining_invoice_exists = select(Invoice.id).where(Invoice.client_id == Client.id).exists()

    # Capture the PDF paths before the rows go away.
    doomed_pdfs = [
        path
        for path in (
            await session.execute(select(Invoice.pdf_path).where(invoice_filter))
        ).scalars()
        if path
    ]

    invoice_count = int(
        (await session.execute(select(func.count(Invoice.id)).where(invoice_filter))).scalar() or 0
    )
    invoice_ids = select(Invoice.id).where(invoice_filter)
    await session.execute(delete(InvoiceItem).where(InvoiceItem.invoice_id.in_(invoice_ids)))
    await session.execute(delete(Invoice).where(invoice_filter))

    client_count = int(
        (
            await session.execute(
                select(func.count(Client.id)).where(client_filter, ~remaining_invoice_exists)
            )
        ).scalar()
        or 0
    )
    await session.execute(delete(Client).where(client_filter, ~remaining_invoice_exists))

    pdfs_deleted = delete_invoice_pdf_files(doomed_pdfs)

    return {
        "invoices_deleted": invoice_count,
        "clients_deleted": client_count,
        "pdfs_deleted": pdfs_deleted,
    }
