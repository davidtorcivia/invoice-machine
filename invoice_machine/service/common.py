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


def line_item_total(unit_price: Decimal | float | int | str, quantity: Decimal | float | int | str) -> Decimal:
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


def format_currency(amount: Decimal | float, currency_code: str = "USD") -> str:
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


def validate_recurring_schedule(
    frequency: str,
    schedule_day: int,
    payment_terms_days: int | None = None,
    tax_rate: Decimal | None = None,
) -> None:
    """Validate recurring schedule cadence and financial fields."""
    if frequency not in VALID_RECURRING_FREQUENCIES:
        raise ValueError(
            f"Invalid frequency. Must be one of: {list(VALID_RECURRING_FREQUENCIES)}"
        )

    if frequency == "weekly" and not (0 <= schedule_day <= 6):
        raise ValueError("For weekly frequency, schedule_day must be 0-6 (Monday-Sunday)")

    if frequency in {"monthly", "quarterly", "yearly"} and not (1 <= schedule_day <= 31):
        raise ValueError("For monthly/quarterly/yearly frequency, schedule_day must be 1-31")

    if payment_terms_days is not None and not (0 <= payment_terms_days <= 365):
        raise ValueError("Payment terms must be between 0 and 365 days")

    if tax_rate is not None and (tax_rate < 0 or tax_rate > 100):
        raise ValueError("Tax rate must be between 0 and 100")


async def purge_trashed_records(
    session: AsyncSession,
    deleted_before: datetime | None = None,
) -> dict[str, int]:
    """Delete trashed invoices and only then delete unreferenced trashed clients."""
    invoice_conditions = [Invoice.deleted_at.is_not(None)]
    client_conditions = [Client.deleted_at.is_not(None)]
    if deleted_before is not None:
        invoice_conditions.append(Invoice.deleted_at < deleted_before)
        client_conditions.append(Client.deleted_at < deleted_before)

    invoice_filter = and_(*invoice_conditions)
    client_filter = and_(*client_conditions)
    remaining_invoice_exists = select(Invoice.id).where(Invoice.client_id == Client.id).exists()

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

    return {
        "invoices_deleted": invoice_count,
        "clients_deleted": client_count,
    }
