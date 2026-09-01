"""Invoice and invoice item MCP tools."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from invoice_machine.presenters import dump_json_list, serialize_invoice, serialize_invoice_item
from invoice_machine.services import InvoiceService
from invoice_machine.utils import utc_now

from .annotations import ADDITIVE, ADDITIVE_IDEMPOTENT, DESTRUCTIVE, READ_ONLY, UPDATE
from .context import get_session, mcp
from .schemas import InvoiceItemOut, InvoiceOut


@mcp.tool(annotations=READ_ONLY)
async def list_invoices(
    status: str | None = None,
    document_type: str | None = None,
    client_id: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    include_deleted: bool = False,
    limit: int = 50,
) -> list[InvoiceOut]:
    """
    List invoices with optional filters. Summary info only, no line items.

    Args:
        status: Filter by status (draft, sent, paid, overdue, cancelled)
        document_type: Filter by type ("invoice" or "quote")
        from_date: Filter from this date (ISO format, e.g. 2025-01-15)
        to_date: Filter to this date (ISO format)
    """
    async with get_session() as session:
        from_date_parsed = date.fromisoformat(from_date) if from_date else None
        to_date_parsed = date.fromisoformat(to_date) if to_date else None

        invoices = await InvoiceService.list_invoices(
            session,
            status=status,
            document_type=document_type,
            client_id=client_id,
            from_date=from_date_parsed,
            to_date=to_date_parsed,
            include_deleted=include_deleted,
            limit=limit,
        )

        return [
            serialize_invoice(
                invoice,
                include_items=False,
                include_formatted_total=True,
                json_ready=True,
                selected_payment_methods_as_list=True,
            )
            for invoice in invoices
        ]


@mcp.tool(annotations=READ_ONLY)
async def get_invoice(invoice_id: int) -> InvoiceOut | None:
    """Get an invoice or quote with its line items."""
    async with get_session() as session:
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            return None
        return serialize_invoice(
            invoice,
            include_items=True,
            include_formatted_total=True,
            json_ready=True,
            selected_payment_methods_as_list=True,
        )


@mcp.tool(annotations=ADDITIVE)
async def create_invoice(
    client_id: int | None = None,
    issue_date: str | None = None,
    due_date: str | None = None,
    payment_terms_days: int | None = None,
    currency_code: str = "USD",
    notes: str | None = None,
    document_type: str = "invoice",
    client_reference: str | None = None,
    show_payment_instructions: bool = True,
    selected_payment_methods: list[str] | None = None,
    invoice_number_override: str | None = None,
    items: list[dict] | None = None,
    tax_enabled: bool | None = None,
    tax_rate: float | None = None,
    tax_name: str | None = None,
) -> InvoiceOut:
    """
    Create a new invoice or quote.

    Args:
        issue_date: Invoice date (ISO format, defaults to today, can be backdated)
        due_date: Explicit due date (ISO format, or auto-calculated from payment_terms)
        payment_terms_days: Payment terms in days (default: from client or business)
        document_type: "invoice" or "quote" (quotes use Q-YYYYMMDD-N numbering)
        selected_payment_methods: List of payment method IDs to show on PDF
        items: List of line items: [{description, quantity, unit_price, unit_type}]
               unit_type can be "qty" (default) or "hours"
        tax_rate: Tax rate percentage (defaults to business profile setting)
        tax_name: Tax name like "VAT" or "Sales Tax" (defaults to business profile setting)
    """
    async with get_session() as session:
        issue_date_parsed = date.fromisoformat(issue_date) if issue_date else utc_now().date()
        due_date_parsed = date.fromisoformat(due_date) if due_date else None

        from decimal import Decimal

        tax_rate_decimal = Decimal(str(tax_rate)) if tax_rate is not None else None

        invoice = await InvoiceService.create_invoice(
            session,
            client_id=client_id,
            issue_date=issue_date_parsed,
            due_date=due_date_parsed,
            payment_terms_days=payment_terms_days,
            currency_code=currency_code,
            notes=notes,
            document_type=document_type,
            client_reference=client_reference,
            show_payment_instructions=show_payment_instructions,
            selected_payment_methods=dump_json_list(selected_payment_methods),
            invoice_number_override=invoice_number_override,
            items=items,
            tax_enabled=tax_enabled,
            tax_rate=tax_rate_decimal,
            tax_name=tax_name,
        )
        return serialize_invoice(
            invoice,
            include_items=True,
            include_formatted_total=True,
            json_ready=True,
            selected_payment_methods_as_list=True,
        )


@mcp.tool(annotations=UPDATE)
async def update_invoice(
    invoice_id: int,
    issue_date: str | None = None,
    due_date: str | None = None,
    status: str | None = None,
    notes: str | None = None,
    document_type: str | None = None,
    client_reference: str | None = None,
    show_payment_instructions: bool | None = None,
    selected_payment_methods: list[str] | None = None,
    tax_enabled: bool | None = None,
    tax_rate: float | None = None,
    tax_name: str | None = None,
) -> InvoiceOut | None:
    """
    Update invoice or quote fields.

    Note: Changing issue_date will regenerate the invoice_number based on the new date.

    Args:
        issue_date: New issue date (ISO format) - changes invoice number!
        due_date: New due date (ISO format)
        status: New status (draft, sent, paid, overdue, cancelled)
        document_type: "invoice" or "quote"
        selected_payment_methods: List of payment method IDs to show on PDF
        tax_enabled: Whether to apply tax (recalculates totals)
        tax_rate: Tax rate percentage (recalculates totals)
        tax_name: Tax name like "VAT" or "Sales Tax"
    """
    async with get_session() as session:
        issue_date_parsed = date.fromisoformat(issue_date) if issue_date else None
        due_date_parsed = date.fromisoformat(due_date) if due_date else None

        update_kwargs = {}
        if issue_date_parsed:
            update_kwargs["issue_date"] = issue_date_parsed
        if due_date_parsed:
            update_kwargs["due_date"] = due_date_parsed
        if status is not None:
            update_kwargs["status"] = status
        if notes is not None:
            update_kwargs["notes"] = notes
        if document_type is not None:
            update_kwargs["document_type"] = document_type
        if client_reference is not None:
            update_kwargs["client_reference"] = client_reference
        if show_payment_instructions is not None:
            update_kwargs["show_payment_instructions"] = show_payment_instructions
        if selected_payment_methods is not None:
            update_kwargs["selected_payment_methods"] = dump_json_list(selected_payment_methods)
        if tax_enabled is not None:
            update_kwargs["tax_enabled"] = 1 if tax_enabled else 0
        if tax_rate is not None:
            update_kwargs["tax_rate"] = Decimal(str(tax_rate))
        if tax_name is not None:
            update_kwargs["tax_name"] = tax_name

        invoice = await InvoiceService.update_invoice(
            session,
            invoice_id,
            **update_kwargs,
        )

        if not invoice:
            return None
        return serialize_invoice(
            invoice,
            include_items=False,
            include_formatted_total=True,
            json_ready=True,
            selected_payment_methods_as_list=True,
        )


@mcp.tool(annotations=ADDITIVE)
async def convert_quote_to_invoice(
    quote_id: int,
    issue_date: str | None = None,
    payment_terms_days: int | None = None,
    invoice_number_override: str | None = None,
) -> dict:
    """
    Create an invoice from an accepted quote, keeping the quote intact.

    The two are linked (the quote gains converted_to_invoice_id, the invoice
    gains converted_from_invoice_id), and line items, tax snapshot, currency and
    payment settings carry over, so the client is billed what they accepted.

    Args:
        quote_id: The quote's ID (document_type must be "quote")
        issue_date: Invoice date (ISO format, defaults to today UTC)
    """
    async with get_session() as session:
        try:
            invoice = await InvoiceService.convert_quote_to_invoice(
                session,
                quote_id,
                issue_date=date.fromisoformat(issue_date) if issue_date else None,
                payment_terms_days=payment_terms_days,
                invoice_number_override=invoice_number_override,
            )
        except ValueError as exc:
            await session.rollback()
            return {"success": False, "error": str(exc)}

        if invoice is None:
            return {"success": False, "error": f"Quote {quote_id} not found"}

        return {
            "success": True,
            "invoice": serialize_invoice(
                invoice,
                include_items=True,
                include_formatted_total=True,
                json_ready=True,
                selected_payment_methods_as_list=True,
            ),
        }


@mcp.tool(annotations=DESTRUCTIVE)
async def delete_invoice(invoice_id: int) -> bool:
    """Move invoice to trash (soft delete)."""
    async with get_session() as session:
        return await InvoiceService.delete_invoice(session, invoice_id)


@mcp.tool(annotations=ADDITIVE_IDEMPOTENT)
async def restore_invoice(invoice_id: int) -> bool:
    """Restore an invoice from trash."""
    async with get_session() as session:
        return await InvoiceService.restore_invoice(session, invoice_id)


@mcp.tool(annotations=ADDITIVE)
async def add_invoice_item(
    invoice_id: int,
    description: str,
    quantity: float | str = 1,
    unit_price: float | str = 0,
    unit_type: str = "qty",
) -> InvoiceItemOut:
    """
    Add a line item to an invoice.

    Args:
        quantity: Quantity or hours, fractional allowed (e.g. 1.5, 0.25) (default: 1)
        unit_price: Unit price or hourly rate
        unit_type: "qty" for quantity or "hours" for time-based billing (default: qty)
    """
    async with get_session() as session:
        try:
            item = await InvoiceService.add_item(
                session,
                invoice_id,
                description,
                quantity,
                Decimal(str(unit_price)),
                unit_type=unit_type,
            )
        except ValueError as exc:
            await session.rollback()
            return {"success": False, "error": str(exc)}

        if item is None:
            return {"success": False, "error": f"Invoice {invoice_id} not found"}
        return serialize_invoice_item(item)


@mcp.tool(annotations=UPDATE)
async def update_invoice_item(
    item_id: int,
    description: str | None = None,
    quantity: float | str | None = None,
    unit_price: float | str | None = None,
    unit_type: str | None = None,
) -> InvoiceItemOut | None:
    """
    Update a line item.

    Args:
        quantity: New quantity or hours, fractional allowed (e.g. 1.5, 0.25)
        unit_price: New unit price or hourly rate
        unit_type: "qty" for quantity or "hours" for time-based billing
    """
    async with get_session() as session:
        updates = {
            k: v for k, v in locals().items() if v is not None and k not in ("item_id", "session")
        }

        item = await InvoiceService.update_item(session, item_id, **updates)

        if not item:
            return None

        return serialize_invoice_item(item)


@mcp.tool(annotations=DESTRUCTIVE)
async def remove_invoice_item(item_id: int) -> bool:
    """Remove a line item from its invoice."""
    async with get_session() as session:
        return await InvoiceService.remove_item(session, item_id)
