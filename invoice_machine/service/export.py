"""CSV export of invoices, line items, payments and clients.

Rows are produced as an async generator so a large export streams to the client
instead of being buffered in memory, and money is emitted as plain decimal
strings (no currency symbols, no thousands separators) alongside an explicit
currency column — that is what spreadsheets and accounting imports expect.
"""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import Client, Invoice, InvoiceItem, Payment
from invoice_machine.service.common import format_quantity, quantize_money

# Excel only auto-detects UTF-8 in a CSV when it starts with a BOM; without it,
# non-ASCII client names arrive mojibaked.
UTF8_BOM = "﻿"

EXPORT_KINDS = ("invoices", "line_items", "payments", "clients")


def _csv_line(row: list) -> str:
    """Render one CSV row (handles quoting/escaping)."""
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow(
        ["" if value is None else value for value in row]
    )
    return buffer.getvalue()


def _date_str(value) -> str:
    return value.isoformat() if value else ""


def _invoice_conditions(
    from_date: date | None,
    to_date: date | None,
    include_deleted: bool,
    document_type: str | None,
):
    conditions = []
    if not include_deleted:
        conditions.append(Invoice.deleted_at.is_(None))
    if document_type:
        conditions.append(Invoice.document_type == document_type)
    if from_date:
        conditions.append(Invoice.issue_date >= from_date)
    if to_date:
        conditions.append(Invoice.issue_date <= to_date)
    return conditions


async def _export_invoices(
    session: AsyncSession,
    from_date: date | None,
    to_date: date | None,
    include_deleted: bool,
    document_type: str | None,
) -> AsyncIterator[str]:
    yield UTF8_BOM + _csv_line(
        [
            "invoice_number",
            "document_type",
            "status",
            "issue_date",
            "due_date",
            "client_name",
            "client_business",
            "client_email",
            "client_reference",
            "currency_code",
            "subtotal",
            "tax_name",
            "tax_rate",
            "tax_amount",
            "total",
            "amount_paid",
            "amount_due",
            "paid_at",
            "exchange_rate",
            "base_currency_code",
            "notes",
            "deleted_at",
        ]
    )

    conditions = _invoice_conditions(from_date, to_date, include_deleted, document_type)
    query = select(Invoice).order_by(Invoice.issue_date, Invoice.id)
    if conditions:
        query = query.where(*conditions)

    # yield_per streams rows instead of materializing the whole result set.
    result = await session.stream(query.execution_options(yield_per=200))
    async for invoice in result.scalars():
        yield _csv_line(
            [
                invoice.invoice_number,
                invoice.document_type,
                invoice.status,
                _date_str(invoice.issue_date),
                _date_str(invoice.due_date),
                invoice.client_name,
                invoice.client_business,
                invoice.client_email,
                invoice.client_reference,
                invoice.currency_code,
                str(quantize_money(invoice.subtotal or 0)),
                invoice.tax_name,
                str(invoice.tax_rate or 0),
                str(quantize_money(invoice.tax_amount or 0)),
                str(quantize_money(invoice.total or 0)),
                str(quantize_money(invoice.amount_paid or 0)),
                str(invoice.amount_due),
                _date_str(invoice.paid_at),
                str(invoice.exchange_rate) if invoice.exchange_rate is not None else "",
                invoice.base_currency_code,
                invoice.notes,
                _date_str(invoice.deleted_at),
            ]
        )


async def _export_line_items(
    session: AsyncSession,
    from_date: date | None,
    to_date: date | None,
    include_deleted: bool,
    document_type: str | None,
) -> AsyncIterator[str]:
    yield UTF8_BOM + _csv_line(
        [
            "invoice_number",
            "document_type",
            "status",
            "issue_date",
            "client_name",
            "currency_code",
            "description",
            "quantity",
            "unit_type",
            "unit_price",
            "line_total",
        ]
    )

    conditions = _invoice_conditions(from_date, to_date, include_deleted, document_type)
    query = (
        select(InvoiceItem, Invoice)
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .order_by(Invoice.issue_date, Invoice.id, InvoiceItem.sort_order)
    )
    if conditions:
        query = query.where(*conditions)

    result = await session.stream(query.execution_options(yield_per=200))
    async for item, invoice in result:
        yield _csv_line(
            [
                invoice.invoice_number,
                invoice.document_type,
                invoice.status,
                _date_str(invoice.issue_date),
                invoice.client_business or invoice.client_name,
                invoice.currency_code,
                item.description,
                format_quantity(item.quantity),
                item.unit_type,
                str(item.unit_price),
                str(item.total),
            ]
        )


async def _export_payments(
    session: AsyncSession,
    from_date: date | None,
    to_date: date | None,
    include_deleted: bool,
    document_type: str | None,
) -> AsyncIterator[str]:
    del document_type  # payments belong to invoices, not quotes

    yield UTF8_BOM + _csv_line(
        [
            "payment_date",
            "invoice_number",
            "client_name",
            "currency_code",
            "amount",
            "method",
            "reference",
            "provider",
            "external_id",
            "notes",
        ]
    )

    conditions = []
    if not include_deleted:
        conditions.append(Invoice.deleted_at.is_(None))
    if from_date:
        conditions.append(Payment.payment_date >= from_date)
    if to_date:
        conditions.append(Payment.payment_date <= to_date)

    query = (
        select(Payment, Invoice)
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .order_by(Payment.payment_date, Payment.id)
    )
    if conditions:
        query = query.where(*conditions)

    result = await session.stream(query.execution_options(yield_per=200))
    async for payment, invoice in result:
        yield _csv_line(
            [
                _date_str(payment.payment_date),
                invoice.invoice_number,
                invoice.client_business or invoice.client_name,
                payment.currency_code,
                str(quantize_money(payment.amount)),
                payment.method,
                payment.reference,
                payment.provider,
                payment.external_id,
                payment.notes,
            ]
        )


async def _export_clients(
    session: AsyncSession,
    from_date: date | None,
    to_date: date | None,
    include_deleted: bool,
    document_type: str | None,
) -> AsyncIterator[str]:
    del from_date, to_date, document_type  # not meaningful for the client list

    yield UTF8_BOM + _csv_line(
        [
            "name",
            "business_name",
            "email",
            "phone",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
            "payment_terms_days",
            "preferred_currency",
            "tax_enabled",
            "tax_rate",
            "tax_name",
            "notes",
            "created_at",
            "deleted_at",
        ]
    )

    query = select(Client).order_by(Client.id)
    if not include_deleted:
        query = query.where(Client.deleted_at.is_(None))

    result = await session.stream(query.execution_options(yield_per=200))
    async for client in result.scalars():
        yield _csv_line(
            [
                client.name,
                client.business_name,
                client.email,
                client.phone,
                client.address_line1,
                client.address_line2,
                client.city,
                client.state,
                client.postal_code,
                client.country,
                client.payment_terms_days,
                client.preferred_currency,
                "" if client.tax_enabled is None else bool(client.tax_enabled),
                str(client.tax_rate) if client.tax_rate is not None else "",
                client.tax_name,
                client.notes,
                _date_str(client.created_at),
                _date_str(client.deleted_at),
            ]
        )


_EXPORTERS = {
    "invoices": _export_invoices,
    "line_items": _export_line_items,
    "payments": _export_payments,
    "clients": _export_clients,
}


def export_csv(
    session: AsyncSession,
    kind: str,
    from_date: date | None = None,
    to_date: date | None = None,
    include_deleted: bool = False,
    document_type: str | None = None,
) -> AsyncIterator[str]:
    """Return an async generator of CSV chunks for the requested export kind."""
    exporter = _EXPORTERS.get(kind)
    if exporter is None:
        raise ValueError(f"Unknown export kind. Must be one of: {list(EXPORT_KINDS)}")
    return exporter(session, from_date, to_date, include_deleted, document_type)


async def export_csv_text(
    session: AsyncSession,
    kind: str,
    from_date: date | None = None,
    to_date: date | None = None,
    include_deleted: bool = False,
    document_type: str | None = None,
    max_rows: int | None = None,
) -> str:
    """Collect an export into a single string (for MCP tools and tests).

    ``max_rows`` caps the body (excluding the header) so an MCP client can't pull
    an unbounded ledger into a model context; truncation is stated in the output.
    """
    chunks: list[str] = []
    rows = 0
    truncated = False
    async for chunk in export_csv(
        session, kind, from_date, to_date, include_deleted, document_type
    ):
        if chunks and max_rows is not None and rows >= max_rows:
            truncated = True
            break
        if chunks:
            rows += 1
        chunks.append(chunk)

    if truncated:
        chunks.append(f"# truncated at {max_rows} rows\n")
    return "".join(chunks)
