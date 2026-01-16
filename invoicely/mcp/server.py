"""MCP server for Claude Desktop integration."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from mcp.server.fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession

from invoicely.database import async_session_maker, BusinessProfile
from invoicely.services import ClientService, InvoiceService, format_currency
from invoicely.config import get_settings

mcp = FastMCP("invoicely")
settings = get_settings()


def get_session() -> AsyncSession:
    """Get database session."""
    return async_session_maker()


# ============================================================================
# Business Profile Tools
# ============================================================================


@mcp.tool()
async def get_business_profile() -> dict:
    """
    Retrieve the current business profile.

    Returns:
        Business profile information including name, address, contact details,
        invoice defaults, and payment methods configuration.
    """
    import json

    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        # Parse payment methods from JSON
        payment_methods = []
        if profile.payment_methods:
            try:
                payment_methods = json.loads(profile.payment_methods)
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "id": profile.id,
            "name": profile.name,
            "business_name": profile.business_name,
            "address_line1": profile.address_line1,
            "address_line2": profile.address_line2,
            "city": profile.city,
            "state": profile.state,
            "postal_code": profile.postal_code,
            "country": profile.country,
            "email": profile.email,
            "phone": profile.phone,
            "ein": profile.ein,
            "logo_path": profile.logo_path,
            "accent_color": profile.accent_color,
            "default_payment_terms_days": profile.default_payment_terms_days,
            "default_notes": profile.default_notes,
            "default_payment_instructions": profile.default_payment_instructions,
            "payment_methods": payment_methods,
            "theme_preference": profile.theme_preference,
        }


@mcp.tool()
async def update_business_profile(
    name: Optional[str] = None,
    business_name: Optional[str] = None,
    address_line1: Optional[str] = None,
    address_line2: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    country: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    ein: Optional[str] = None,
    accent_color: Optional[str] = None,
    default_payment_terms_days: Optional[int] = None,
    default_notes: Optional[str] = None,
    default_payment_instructions: Optional[str] = None,
    theme_preference: Optional[str] = None,
) -> dict:
    """
    Update business profile fields.

    Only provide the fields you want to change. All parameters are optional.

    Args:
        name: Your personal name
        business_name: Business/legal entity name
        address_line1: Street address
        address_line2: Apartment/suite number
        city: City
        state: State/province
        postal_code: ZIP/postal code
        country: Country
        email: Contact email
        phone: Phone number
        ein: Tax ID / EIN
        accent_color: PDF accent color (hex format, e.g. #0891b2)
        default_payment_terms_days: Default payment terms (e.g. 30 for Net 30)
        default_notes: Default invoice footer notes
        default_payment_instructions: Fallback payment instructions text
        theme_preference: UI theme preference (system, light, dark)

    Returns:
        Updated business profile
    """
    import json

    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        updates = {k: v for k, v in locals().items() if v is not None and k not in ("session", "json")}
        for key, value in updates.items():
            setattr(profile, key, value)

        profile.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(profile)

        # Parse payment methods from JSON
        payment_methods = []
        if profile.payment_methods:
            try:
                payment_methods = json.loads(profile.payment_methods)
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "id": profile.id,
            "name": profile.name,
            "business_name": profile.business_name,
            "address_line1": profile.address_line1,
            "address_line2": profile.address_line2,
            "city": profile.city,
            "state": profile.state,
            "postal_code": profile.postal_code,
            "country": profile.country,
            "email": profile.email,
            "phone": profile.phone,
            "ein": profile.ein,
            "logo_path": profile.logo_path,
            "accent_color": profile.accent_color,
            "default_payment_terms_days": profile.default_payment_terms_days,
            "default_notes": profile.default_notes,
            "default_payment_instructions": profile.default_payment_instructions,
            "payment_methods": payment_methods,
            "theme_preference": profile.theme_preference,
        }


@mcp.tool()
async def add_payment_method(
    name: str,
    instructions: str,
) -> dict:
    """
    Add a new payment method to the business profile.

    Payment methods can be selected individually per invoice to show
    specific payment options on the PDF.

    Args:
        name: Payment method name (e.g., "Bank Transfer (ACH)", "Venmo", "Zelle")
        instructions: Payment details (e.g., bank account info, username, etc.)

    Returns:
        The created payment method with its ID
    """
    import json

    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        # Parse existing methods
        payment_methods = []
        if profile.payment_methods:
            try:
                payment_methods = json.loads(profile.payment_methods)
            except (json.JSONDecodeError, TypeError):
                pass

        # Create new method with unique ID
        new_method = {
            "id": str(int(datetime.utcnow().timestamp() * 1000)),
            "name": name,
            "instructions": instructions,
        }
        payment_methods.append(new_method)

        # Save back to profile
        profile.payment_methods = json.dumps(payment_methods)
        profile.updated_at = datetime.utcnow()
        await session.commit()

        return new_method


@mcp.tool()
async def remove_payment_method(method_id: str) -> bool:
    """
    Remove a payment method from the business profile.

    Args:
        method_id: The payment method's ID

    Returns:
        True if removed, False if not found
    """
    import json

    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        # Parse existing methods
        payment_methods = []
        if profile.payment_methods:
            try:
                payment_methods = json.loads(profile.payment_methods)
            except (json.JSONDecodeError, TypeError):
                pass

        # Find and remove the method
        original_count = len(payment_methods)
        payment_methods = [m for m in payment_methods if m.get("id") != method_id]

        if len(payment_methods) == original_count:
            return False

        # Save back to profile
        profile.payment_methods = json.dumps(payment_methods)
        profile.updated_at = datetime.utcnow()
        await session.commit()

        return True


# ============================================================================
# Client Tools
# ============================================================================


@mcp.tool()
async def list_clients(
    search: Optional[str] = None,
    include_deleted: bool = False,
) -> list:
    """
    List all clients.

    Args:
        search: Optional search term to filter by name or business name
        include_deleted: Whether to include soft-deleted clients

    Returns:
        List of clients with their details
    """
    async with get_session() as session:
        clients = await ClientService.list_clients(session, search=search, include_deleted=include_deleted)
        return [
            {
                "id": c.id,
                "name": c.name,
                "business_name": c.business_name,
                "display_name": c.display_name,
                "email": c.email,
                "phone": c.phone,
                "payment_terms_days": c.payment_terms_days,
                "notes": c.notes,
                "is_active": c.is_active,
            }
            for c in clients
        ]


@mcp.tool()
async def get_client(client_id: int) -> Optional[dict]:
    """
    Get client by ID.

    Args:
        client_id: The client's ID

    Returns:
        Client details or null if not found
    """
    async with get_session() as session:
        client = await ClientService.get_client(session, client_id)
        if not client:
            return None

        return {
            "id": client.id,
            "name": client.name,
            "business_name": client.business_name,
            "display_name": client.display_name,
            "address_line1": client.address_line1,
            "address_line2": client.address_line2,
            "city": client.city,
            "state": client.state,
            "postal_code": client.postal_code,
            "country": client.country,
            "email": client.email,
            "phone": client.phone,
            "payment_terms_days": client.payment_terms_days,
            "notes": client.notes,
        }


@mcp.tool()
async def create_client(
    name: Optional[str] = None,
    business_name: Optional[str] = None,
    address_line1: Optional[str] = None,
    address_line2: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    country: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    payment_terms_days: int = 30,
    notes: Optional[str] = None,
) -> dict:
    """
    Create a new client.

    At minimum, provide either name or business_name to identify the client.

    Args:
        name: Contact person's name
        business_name: Company/business name
        address_line1: Street address
        address_line2: Apartment/suite number
        city: City
        state: State/province
        postal_code: ZIP/postal code
        country: Country
        email: Contact email
        phone: Phone number
        payment_terms_days: Default payment terms for this client (default: 30)
        notes: Additional notes

    Returns:
        Created client with ID
    """
    async with get_session() as session:
        client = await ClientService.create_client(
            session,
            name=name,
            business_name=business_name,
            address_line1=address_line1,
            address_line2=address_line2,
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
            email=email,
            phone=phone,
            payment_terms_days=payment_terms_days,
            notes=notes,
        )

        return {
            "id": client.id,
            "name": client.name,
            "business_name": client.business_name,
            "display_name": client.display_name,
            "email": client.email,
            "phone": client.phone,
            "payment_terms_days": client.payment_terms_days,
            "notes": client.notes,
        }


@mcp.tool()
async def update_client(
    client_id: int,
    name: Optional[str] = None,
    business_name: Optional[str] = None,
    address_line1: Optional[str] = None,
    address_line2: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
    country: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    payment_terms_days: Optional[int] = None,
    notes: Optional[str] = None,
) -> Optional[dict]:
    """
    Update client fields.

    Only provide the fields you want to change.

    Args:
        client_id: The client's ID
        name: Contact person's name
        business_name: Company/business name
        address_line1: Street address
        address_line2: Apartment/suite number
        city: City
        state: State/province
        postal_code: ZIP/postal code
        country: Country
        email: Contact email
        phone: Phone number
        payment_terms_days: Default payment terms for this client
        notes: Additional notes

    Returns:
        Updated client or null if not found
    """
    async with get_session() as session:
        updates = {k: v for k, v in locals().items() if v is not None and k not in ("client_id", "session")}
        client = await ClientService.update_client(session, client_id, **updates)

        if not client:
            return None

        return {
            "id": client.id,
            "name": client.name,
            "business_name": client.business_name,
            "display_name": client.display_name,
            "email": client.email,
            "phone": client.phone,
            "payment_terms_days": client.payment_terms_days,
            "notes": client.notes,
        }


@mcp.tool()
async def delete_client(client_id: int) -> bool:
    """
    Move client to trash (soft delete).

    Args:
        client_id: The client's ID

    Returns:
        True if deleted, False if not found
    """
    async with get_session() as session:
        return await ClientService.delete_client(session, client_id)


@mcp.tool()
async def restore_client(client_id: int) -> bool:
    """
    Restore a client from trash.

    Args:
        client_id: The client's ID

    Returns:
        True if restored, False if not found
    """
    async with get_session() as session:
        return await ClientService.restore_client(session, client_id)


# ============================================================================
# Invoice Tools
# ============================================================================


@mcp.tool()
async def list_invoices(
    status: Optional[str] = None,
    client_id: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
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
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "document_type": getattr(inv, "document_type", "invoice"),
                "client_id": inv.client_id,
                "client_name": inv.client_business or inv.client_name or "Unknown",
                "status": inv.status,
                "issue_date": inv.issue_date.isoformat(),
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "currency_code": inv.currency_code,
                "total": str(inv.total),
                "total_formatted": format_currency(inv.total, inv.currency_code),
                "created_at": inv.created_at.isoformat(),
            }
            for inv in invoices
        ]


@mcp.tool()
async def get_invoice(invoice_id: int) -> Optional[dict]:
    """
    Get invoice or quote with line items.

    Args:
        invoice_id: The invoice/quote ID

    Returns:
        Full invoice/quote details with line items, or null if not found
    """
    import json

    async with get_session() as session:
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            return None

        # Parse selected payment methods
        selected_payment_methods = []
        if getattr(invoice, "selected_payment_methods", None):
            try:
                selected_payment_methods = json.loads(invoice.selected_payment_methods)
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "document_type": getattr(invoice, "document_type", "invoice"),
            "client_id": invoice.client_id,
            "client_name": invoice.client_name,
            "client_business": invoice.client_business,
            "client_address": invoice.client_address,
            "client_email": invoice.client_email,
            "client_reference": getattr(invoice, "client_reference", None),
            "status": invoice.status,
            "issue_date": invoice.issue_date.isoformat(),
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "payment_terms_days": invoice.payment_terms_days,
            "currency_code": invoice.currency_code,
            "subtotal": str(invoice.subtotal),
            "total": str(invoice.total),
            "total_formatted": format_currency(invoice.total, invoice.currency_code),
            "notes": invoice.notes,
            "show_payment_instructions": bool(getattr(invoice, "show_payment_instructions", True)),
            "selected_payment_methods": selected_payment_methods,
            "pdf_generated_at": invoice.pdf_generated_at.isoformat() if invoice.pdf_generated_at else None,
            "items": [
                {
                    "id": item.id,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_type": getattr(item, "unit_type", "qty"),
                    "unit_price": str(item.unit_price),
                    "total": str(item.total),
                }
                for item in invoice.items
            ],
        }


@mcp.tool()
async def create_invoice(
    client_id: Optional[int] = None,
    issue_date: Optional[str] = None,
    due_date: Optional[str] = None,
    payment_terms_days: Optional[int] = None,
    currency_code: str = "USD",
    notes: Optional[str] = None,
    document_type: str = "invoice",
    client_reference: Optional[str] = None,
    show_payment_instructions: bool = True,
    selected_payment_methods: Optional[list[str]] = None,
    invoice_number_override: Optional[str] = None,
    items: Optional[list[dict]] = None,
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

    Returns:
        Created invoice/quote with generated number
    """
    import json

    async with get_session() as session:
        issue_date_parsed = date.fromisoformat(issue_date) if issue_date else date.today()
        due_date_parsed = date.fromisoformat(due_date) if due_date else None

        # Convert selected_payment_methods to JSON string
        selected_methods_json = None
        if selected_payment_methods:
            selected_methods_json = json.dumps(selected_payment_methods)

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
            selected_payment_methods=selected_methods_json,
            invoice_number_override=invoice_number_override,
            items=items,
        )

        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "document_type": getattr(invoice, "document_type", "invoice"),
            "client_id": invoice.client_id,
            "client_name": invoice.client_business or invoice.client_name or "Unknown",
            "client_reference": getattr(invoice, "client_reference", None),
            "status": invoice.status,
            "issue_date": invoice.issue_date.isoformat(),
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "currency_code": invoice.currency_code,
            "total": str(invoice.total),
            "total_formatted": format_currency(invoice.total, invoice.currency_code),
            "items": [
                {"id": item.id, "description": item.description, "quantity": item.quantity,
                 "unit_type": getattr(item, "unit_type", "qty"),
                 "unit_price": str(item.unit_price), "total": str(item.total)}
                for item in invoice.items
            ],
        }


@mcp.tool()
async def update_invoice(
    invoice_id: int,
    issue_date: Optional[str] = None,
    due_date: Optional[str] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    document_type: Optional[str] = None,
    client_reference: Optional[str] = None,
    show_payment_instructions: Optional[bool] = None,
    selected_payment_methods: Optional[list[str]] = None,
) -> Optional[dict]:
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
    import json

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
            update_kwargs["selected_payment_methods"] = json.dumps(selected_payment_methods)

        invoice = await InvoiceService.update_invoice(
            session,
            invoice_id,
            **update_kwargs,
        )

        if not invoice:
            return None

        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "document_type": getattr(invoice, "document_type", "invoice"),
            "client_id": invoice.client_id,
            "client_reference": getattr(invoice, "client_reference", None),
            "status": invoice.status,
            "issue_date": invoice.issue_date.isoformat(),
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "total": str(invoice.total),
            "total_formatted": format_currency(invoice.total, invoice.currency_code),
        }


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

        return {
            "id": item.id,
            "description": item.description,
            "quantity": item.quantity,
            "unit_type": getattr(item, "unit_type", "qty"),
            "unit_price": str(item.unit_price),
            "total": str(item.total),
        }


@mcp.tool()
async def update_invoice_item(
    item_id: int,
    description: Optional[str] = None,
    quantity: Optional[int] = None,
    unit_price: Optional[float | str] = None,
    unit_type: Optional[str] = None,
) -> Optional[dict]:
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

        return {
            "id": item.id,
            "description": item.description,
            "quantity": item.quantity,
            "unit_type": getattr(item, "unit_type", "qty"),
            "unit_price": str(item.unit_price),
            "total": str(item.total),
        }


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


# ============================================================================
# PDF Generation
# ============================================================================


@mcp.tool()
async def generate_pdf(invoice_id: int) -> dict:
    """
    Generate or regenerate PDF for an invoice.

    Args:
        invoice_id: The invoice's ID

    Returns:
        {
            "invoice_id": 123,
            "invoice_number": "20250115-1",
            "pdf_url": "http://localhost:8080/api/invoices/123/pdf",
            "generated_at": "2025-01-15T10:30:00Z"
        }
    """
    from datetime import datetime
    from invoicely.pdf.generator import generate_pdf as do_generate_pdf

    async with get_session() as session:
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            return {"error": "Invoice not found"}

        pdf_path = await do_generate_pdf(session, invoice)

        invoice.pdf_path = pdf_path
        invoice.pdf_generated_at = datetime.utcnow()
        await session.commit()

        return {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "pdf_url": f"{settings.app_base_url}/api/invoices/{invoice.id}/pdf",
            "generated_at": invoice.pdf_generated_at.isoformat(),
        }


# ============================================================================
# Trash Management
# ============================================================================


@mcp.tool()
async def list_trash() -> list:
    """
    List all trashed invoices and clients.

    Returns:
        List of trashed items with days until auto-purge
    """
    from datetime import timedelta

    async with get_session() as session:
        from sqlalchemy import select

        items = []

        # Trashed clients
        client_result = await session.execute(
            select(invoicely.database.Client).where(
                invoicely.database.Client.deleted_at.is_not(None)
            )
        )
        for client in client_result.scalars():
            days_left = settings.trash_retention_days - int(
                (datetime.utcnow() - client.deleted_at).total_seconds() / 86400
            )
            items.append({
                "type": "client",
                "id": client.id,
                "name": client.display_name,
                "deleted_at": client.deleted_at.isoformat(),
                "days_until_purge": days_left,
            })

        # Trashed invoices
        invoice_result = await session.execute(
            select(invoicely.database.Invoice).where(
                invoicely.database.Invoice.deleted_at.is_not(None)
            )
        )
        for invoice in invoice_result.scalars():
            days_left = settings.trash_retention_days - int(
                (datetime.utcnow() - invoice.deleted_at).total_seconds() / 86400
            )
            items.append({
                "type": "invoice",
                "id": invoice.id,
                "name": invoice.invoice_number,
                "deleted_at": invoice.deleted_at.isoformat(),
                "days_until_purge": days_left,
            })

        items.sort(key=lambda x: x["deleted_at"], reverse=True)
        return items


@mcp.tool()
async def empty_trash() -> dict:
    """
    Permanently delete all items older than retention period.

    Returns:
        Summary of deleted items
    """
    from datetime import timedelta
    from sqlalchemy import delete, and_

    async with get_session() as session:
        purge_threshold = datetime.utcnow() - timedelta(days=settings.trash_retention_days)

        # Count items to be deleted
        from sqlalchemy import select, func

        client_count = await session.execute(
            select(func.count(invoicely.database.Client.id)).where(
                and_(
                    invoicely.database.Client.deleted_at.is_not(None),
                    invoicely.database.Client.deleted_at < purge_threshold,
                )
            )
        )
        invoice_count = await session.execute(
            select(func.count(invoicely.database.Invoice.id)).where(
                and_(
                    invoicely.database.Invoice.deleted_at.is_not(None),
                    invoicely.database.Invoice.deleted_at < purge_threshold,
                )
            )
        )

        clients_deleted = client_count.scalar() or 0
        invoices_deleted = invoice_count.scalar() or 0

        # Delete
        await session.execute(
            delete(invoicely.database.Client).where(
                and_(
                    invoicely.database.Client.deleted_at.is_not(None),
                    invoicely.database.Client.deleted_at < purge_threshold,
                )
            )
        )
        await session.execute(
            delete(invoicely.database.Invoice).where(
                and_(
                    invoicely.database.Invoice.deleted_at.is_not(None),
                    invoicely.database.Invoice.deleted_at < purge_threshold,
                )
            )
        )

        await session.commit()

        return {
            "clients_deleted": clients_deleted,
            "invoices_deleted": invoices_deleted,
        }


# Import for type references
import invoicely.database


def main():
    """Run the MCP server (stdio transport for local use)."""
    mcp.run()


def run_sse_server(host: str = "0.0.0.0", port: int = 8081):
    """
    Run the MCP server with SSE transport for remote access.

    This enables Claude Desktop to connect over HTTP from:
    - Another machine on your LAN
    - Remotely via Cloudflare Tunnel or similar

    Usage:
        python -m invoicely.mcp.server --sse --port 8081
    """
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.requests import Request
    from starlette.responses import Response
    from mcp.server.sse import SseServerTransport

    # Create SSE transport
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        # Check API key if configured
        if settings.mcp_api_key:
            # Check Authorization header
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                provided_key = auth_header[7:]
            else:
                # Also check query param for compatibility
                provided_key = request.query_params.get("api_key", "")

            if provided_key != settings.mcp_api_key:
                return Response("Unauthorized", status_code=401)

        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp._mcp_server.run(
                streams[0], streams[1], mcp._mcp_server.create_initialization_options()
            )
        return Response()

    async def handle_messages(request: Request):
        # Check API key if configured
        if settings.mcp_api_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                provided_key = auth_header[7:]
            else:
                provided_key = request.query_params.get("api_key", "")

            if provided_key != settings.mcp_api_key:
                return Response("Unauthorized", status_code=401)

        await sse.handle_post_message(request.scope, request.receive, request._send)
        return Response()

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages/", endpoint=handle_messages, methods=["POST"]),
        ]
    )

    print(f"Starting MCP SSE server on {host}:{port}")
    if settings.mcp_api_key:
        print("API key authentication is ENABLED")
    else:
        print("WARNING: No MCP_API_KEY set - server is unprotected!")
    print(f"SSE endpoint: http://{host}:{port}/sse")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import sys

    if "--sse" in sys.argv:
        # Parse optional port
        port = 8081
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
        run_sse_server(port=port)
    else:
        main()
