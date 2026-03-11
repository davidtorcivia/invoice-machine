"""Invoice and invoice item MCP tools."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from invoice_machine.presenters import dump_json_list, serialize_invoice, serialize_invoice_item
from invoice_machine.services import InvoiceService

from .context import get_session, mcp


@mcp.tool()
async def list_invoices(
    status: str | None = None,
    client_id: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    include_deleted: bool = False,
    limit: int = 50,
) -> list:
    """
    List invoices with optional filters.

    Args:
        status: Filter by status (draft, sent, paid, overdue, cancelled)
        client_id: Filter by client ID
        from_date: Filter from this date (ISO format, e.g. 2025-01-15)
        to_date: Filter to this date (ISO format)
        include_deleted: Include soft-deleted invoices
        limit: Maximum number of results (default: 50)

    Returns:
        List of invoices with summary info (no line items)
    """
    async with get_session() as session:
        from_date_parsed = date.fromisoformat(from_date) if from_date else None
        to_date_parsed = date.fromisoformat(to_date) if to_date else None

        invoices = await InvoiceService.list_invoices(
            session,
            status=status,
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


@mcp.tool()
async def get_invoice(invoice_id: int) -> dict | None:
    """
    Get invoice or quote with line items.

    Args:
        invoice_id: The invoice/quote ID

    Returns:
        Full invoice/quote details with line items, or null if not found
    """
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


@mcp.tool()
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
) -> dict:
    """
    Create a new invoice or quote.

    Args:
        client_id: Existing client ID (use create_client first if needed)
        issue_date: Invoice date (ISO format, defaults to today, can be backdated)
        due_date: Explicit due date (ISO format, or auto-calculated from payment_terms)
        payment_terms_days: Payment terms in days (default: from client or business)
        currency_code: Currency code (default: USD)
        notes: Footer notes for the invoice
        document_type: "invoice" or "quote" (quotes use Q-YYYYMMDD-N numbering)
        client_reference: Client's PO number or reference
        show_payment_instructions: Whether to show payment details on PDF (default: True)
        selected_payment_methods: List of payment method IDs to show on PDF
        invoice_number_override: Custom invoice/quote number (overrides auto-generation)
        items: List of line items: [{description, quantity, unit_price, unit_type}]
               unit_type can be "qty" (default) or "hours"
        tax_enabled: Whether to apply tax (defaults to business profile setting)
        tax_rate: Tax rate percentage (defaults to business profile setting)
        tax_name: Tax name like "VAT" or "Sales Tax" (defaults to business profile setting)

    Returns:
        Created invoice/quote with generated number
    """
    async with get_session() as session:
        issue_date_parsed = date.fromisoformat(issue_date) if issue_date else date.today()
        due_date_parsed = date.fromisoformat(due_date) if due_date else None

        # Convert tax_rate to Decimal if provided
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


@mcp.tool()
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
) -> dict | None:
    """
    Update invoice or quote fields.

    Note: Changing issue_date will regenerate the invoice_number based on the new date.

    Args:
        invoice_id: The invoice/quote ID
        issue_date: New issue date (ISO format) - changes invoice number!
        due_date: New due date (ISO format)
        status: New status (draft, sent, paid, overdue, cancelled)
        notes: Footer notes
        document_type: "invoice" or "quote"
        client_reference: Client's PO number or reference
        show_payment_instructions: Whether to show payment details on PDF
        selected_payment_methods: List of payment method IDs to show on PDF

    Returns:
        Updated invoice/quote or null if not found
    """
    async with get_session() as session:
        issue_date_parsed = date.fromisoformat(issue_date) if issue_date else None
        due_date_parsed = date.fromisoformat(due_date) if due_date else None

        # Build update kwargs
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


@mcp.tool()
async def delete_invoice(invoice_id: int) -> bool:
    """
    Move invoice to trash (soft delete).

    Args:
        invoice_id: The invoice's ID

    Returns:
        True if deleted, False if not found
    """
    async with get_session() as session:
        return await InvoiceService.delete_invoice(session, invoice_id)


@mcp.tool()
async def restore_invoice(invoice_id: int) -> bool:
    """
    Restore an invoice from trash.

    Args:
        invoice_id: The invoice's ID

    Returns:
        True if restored, False if not found
    """
    async with get_session() as session:
        return await InvoiceService.restore_invoice(session, invoice_id)


# ============================================================================
# Invoice Item Tools
# ============================================================================


@mcp.tool()
async def add_invoice_item(
    invoice_id: int,
    description: str,
    quantity: int = 1,
    unit_price: float | str = 0,
    unit_type: str = "qty",
) -> dict:
    """
    Add a line item to an invoice.

    Args:
        invoice_id: The invoice's ID
        description: Item description
        quantity: Quantity or hours (default: 1)
        unit_price: Unit price or hourly rate
        unit_type: "qty" for quantity or "hours" for time-based billing (default: qty)

    Returns:
        Created line item
    """
    async with get_session() as session:
        item = await InvoiceService.add_item(
            session,
            invoice_id,
            description,
            quantity,
            Decimal(str(unit_price)),
            unit_type=unit_type,
        )

        return serialize_invoice_item(item)


@mcp.tool()
async def update_invoice_item(
    item_id: int,
    description: str | None = None,
    quantity: int | None = None,
    unit_price: float | str | None = None,
    unit_type: str | None = None,
) -> dict | None:
    """
    Update a line item.

    Args:
        item_id: The item's ID
        description: New description
        quantity: New quantity or hours
        unit_price: New unit price or hourly rate
        unit_type: "qty" for quantity or "hours" for time-based billing

    Returns:
        Updated line item or null if not found
    """
    async with get_session() as session:
        updates = {k: v for k, v in locals().items()
                   if v is not None and k not in ("item_id", "session")}

        item = await InvoiceService.update_item(session, item_id, **updates)

        if not item:
            return None

        return serialize_invoice_item(item)


@mcp.tool()
async def remove_invoice_item(item_id: int) -> bool:
    """
    Remove a line item from its invoice.

    Args:
        item_id: The item's ID

    Returns:
        True if removed, False if not found
    """
    async with get_session() as session:
        return await InvoiceService.remove_item(session, item_id)



