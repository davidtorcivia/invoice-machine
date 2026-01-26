"""MCP server for Claude Desktop integration."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Union

from mcp.server.fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import async_session_maker, BusinessProfile, Client, Invoice
from invoice_machine.services import ClientService, InvoiceService, RecurringService, SearchService, format_currency
from invoice_machine.config import get_settings

mcp = FastMCP("invoice-machine")
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
            # Tax settings
            "default_tax_enabled": bool(getattr(profile, "default_tax_enabled", 0)),
            "default_tax_rate": str(getattr(profile, "default_tax_rate", 0)),
            "default_tax_name": getattr(profile, "default_tax_name", "Tax"),
            # SMTP settings (password hidden)
            "smtp_enabled": bool(getattr(profile, "smtp_enabled", 0)),
            "smtp_host": getattr(profile, "smtp_host", None),
            "smtp_port": getattr(profile, "smtp_port", 587),
            "smtp_username": getattr(profile, "smtp_username", None),
            "smtp_password_set": bool(getattr(profile, "smtp_password", None)),
            "smtp_from_email": getattr(profile, "smtp_from_email", None),
            "smtp_from_name": getattr(profile, "smtp_from_name", None),
            "smtp_use_tls": bool(getattr(profile, "smtp_use_tls", 1)),
            # Email template settings
            "email_subject_template": getattr(profile, "email_subject_template", None),
            "email_body_template": getattr(profile, "email_body_template", None),
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
    default_tax_enabled: Optional[bool] = None,
    default_tax_rate: Optional[float] = None,
    default_tax_name: Optional[str] = None,
    smtp_enabled: Optional[bool] = None,
    smtp_host: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_username: Optional[str] = None,
    smtp_password: Optional[str] = None,
    smtp_from_email: Optional[str] = None,
    smtp_from_name: Optional[str] = None,
    smtp_use_tls: Optional[bool] = None,
    email_subject_template: Optional[str] = None,
    email_body_template: Optional[str] = None,
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
        default_tax_enabled: Whether to apply tax by default on new invoices
        default_tax_rate: Default tax rate percentage (e.g. 8.25 for 8.25%)
        default_tax_name: Default tax name (e.g. "VAT", "Sales Tax", "GST")
        smtp_enabled: Enable SMTP email sending
        smtp_host: SMTP server hostname
        smtp_port: SMTP server port (default 587)
        smtp_username: SMTP authentication username
        smtp_password: SMTP authentication password
        smtp_from_email: Sender email address
        smtp_from_name: Sender display name
        smtp_use_tls: Use TLS/STARTTLS (default True)
        email_subject_template: Default email subject template with placeholders
        email_body_template: Default email body template with placeholders

    Returns:
        Updated business profile
    """
    import json
    from decimal import Decimal

    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        updates = {
            k: v
            for k, v in locals().items()
            if v is not None and k not in ("session", "json", "Decimal")
        }

        if "smtp_password" in updates:
            from invoice_machine.crypto import encrypt_credential

            if updates["smtp_password"]:
                updates["smtp_password"] = encrypt_credential(updates["smtp_password"])
            else:
                updates["smtp_password"] = None

        # Convert tax fields to proper types
        if "default_tax_enabled" in updates:
            updates["default_tax_enabled"] = 1 if updates["default_tax_enabled"] else 0
        if "default_tax_rate" in updates:
            updates["default_tax_rate"] = Decimal(str(updates["default_tax_rate"]))

        # Convert SMTP boolean fields to integers
        if "smtp_enabled" in updates:
            updates["smtp_enabled"] = 1 if updates["smtp_enabled"] else 0
        if "smtp_use_tls" in updates:
            updates["smtp_use_tls"] = 1 if updates["smtp_use_tls"] else 0

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
            # Tax settings
            "default_tax_enabled": bool(getattr(profile, "default_tax_enabled", 0)),
            "default_tax_rate": str(getattr(profile, "default_tax_rate", 0)),
            "default_tax_name": getattr(profile, "default_tax_name", "Tax"),
            # SMTP settings (password hidden)
            "smtp_enabled": bool(getattr(profile, "smtp_enabled", 0)),
            "smtp_host": getattr(profile, "smtp_host", None),
            "smtp_port": getattr(profile, "smtp_port", 587),
            "smtp_username": getattr(profile, "smtp_username", None),
            "smtp_password_set": bool(getattr(profile, "smtp_password", None)),
            "smtp_from_email": getattr(profile, "smtp_from_email", None),
            "smtp_from_name": getattr(profile, "smtp_from_name", None),
            "smtp_use_tls": bool(getattr(profile, "smtp_use_tls", 1)),
            # Email template settings
            "email_subject_template": getattr(profile, "email_subject_template", None),
            "email_body_template": getattr(profile, "email_body_template", None),
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
                "tax_enabled": c.tax_enabled,
                "tax_rate": float(c.tax_rate) if c.tax_rate is not None else None,
                "tax_name": c.tax_name,
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
            "tax_enabled": client.tax_enabled,
            "tax_rate": float(client.tax_rate) if client.tax_rate is not None else None,
            "tax_name": client.tax_name,
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
    tax_enabled: Optional[int] = None,
    tax_rate: Optional[float] = None,
    tax_name: Optional[str] = None,
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
        tax_enabled: Per-client tax override (None = use global, 0 = disabled, 1 = enabled)
        tax_rate: Per-client tax rate override (e.g. 8.25 for 8.25%)
        tax_name: Per-client tax name override (e.g. "Sales Tax")

    Returns:
        Created client with ID
    """
    async with get_session() as session:
        # Build kwargs, converting tax_rate to Decimal if provided
        kwargs = {
            "name": name,
            "business_name": business_name,
            "address_line1": address_line1,
            "address_line2": address_line2,
            "city": city,
            "state": state,
            "postal_code": postal_code,
            "country": country,
            "email": email,
            "phone": phone,
            "payment_terms_days": payment_terms_days,
            "notes": notes,
            "tax_enabled": tax_enabled,
            "tax_name": tax_name,
        }
        if tax_rate is not None:
            from decimal import Decimal
            kwargs["tax_rate"] = Decimal(str(tax_rate))

        client = await ClientService.create_client(session, **kwargs)

        return {
            "id": client.id,
            "name": client.name,
            "business_name": client.business_name,
            "display_name": client.display_name,
            "email": client.email,
            "phone": client.phone,
            "payment_terms_days": client.payment_terms_days,
            "notes": client.notes,
            "tax_enabled": client.tax_enabled,
            "tax_rate": float(client.tax_rate) if client.tax_rate is not None else None,
            "tax_name": client.tax_name,
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
    tax_enabled: Optional[int] = None,
    tax_rate: Optional[float] = None,
    tax_name: Optional[str] = None,
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
        tax_enabled: Per-client tax override (None = use global, 0 = disabled, 1 = enabled)
        tax_rate: Per-client tax rate override (e.g. 8.25 for 8.25%)
        tax_name: Per-client tax name override (e.g. "Sales Tax")

    Returns:
        Updated client or null if not found
    """
    async with get_session() as session:
        # Build updates dict, handling tax_rate Decimal conversion
        updates = {}
        local_vars = {
            "name": name, "business_name": business_name,
            "address_line1": address_line1, "address_line2": address_line2,
            "city": city, "state": state, "postal_code": postal_code, "country": country,
            "email": email, "phone": phone, "payment_terms_days": payment_terms_days,
            "notes": notes, "tax_enabled": tax_enabled, "tax_name": tax_name,
        }
        for k, v in local_vars.items():
            if v is not None:
                updates[k] = v

        if tax_rate is not None:
            from decimal import Decimal
            updates["tax_rate"] = Decimal(str(tax_rate))

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
            "tax_enabled": client.tax_enabled,
            "tax_rate": float(client.tax_rate) if client.tax_rate is not None else None,
            "tax_name": client.tax_name,
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
    tax_enabled: Optional[bool] = None,
    tax_rate: Optional[float] = None,
    tax_name: Optional[str] = None,
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
    import json

    async with get_session() as session:
        issue_date_parsed = date.fromisoformat(issue_date) if issue_date else date.today()
        due_date_parsed = date.fromisoformat(due_date) if due_date else None

        # Convert selected_payment_methods to JSON string
        selected_methods_json = None
        if selected_payment_methods:
            selected_methods_json = json.dumps(selected_payment_methods)

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
            selected_payment_methods=selected_methods_json,
            invoice_number_override=invoice_number_override,
            items=items,
            tax_enabled=tax_enabled,
            tax_rate=tax_rate_decimal,
            tax_name=tax_name,
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
            "subtotal": str(invoice.subtotal),
            "tax_enabled": bool(getattr(invoice, "tax_enabled", 0)),
            "tax_rate": str(getattr(invoice, "tax_rate", 0)),
            "tax_name": getattr(invoice, "tax_name", "Tax"),
            "tax_amount": str(getattr(invoice, "tax_amount", 0)),
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
    unit_price: Union[float, str] = 0,
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
    unit_price: Optional[Union[float, str]] = None,
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
    from invoice_machine.pdf.generator import generate_pdf as do_generate_pdf

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
            select(Client).where(
                Client.deleted_at.is_not(None)
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
            select(Invoice).where(
                Invoice.deleted_at.is_not(None)
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


# Note: empty_trash is intentionally not exposed via MCP for security reasons.
# Trash emptying is handled automatically by the scheduled cleanup task or via the web UI.


# ============================================================================
# Analytics Tools
# ============================================================================


@mcp.tool()
async def get_revenue_summary(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    group_by: str = "month",
) -> dict:
    """
    Get revenue summary for the specified period.

    Args:
        from_date: Start date (ISO format, defaults to start of current year)
        to_date: End date (ISO format, defaults to today)
        group_by: How to group breakdown - "month", "quarter", or "year"

    Returns:
        Total invoiced, paid, outstanding, and breakdown by period
    """
    from collections import defaultdict

    async with get_session() as session:
        # Parse dates
        today = date.today()
        from_date_parsed = date.fromisoformat(from_date) if from_date else date(today.year, 1, 1)
        to_date_parsed = date.fromisoformat(to_date) if to_date else today

        # Get all invoices in range (exclude deleted)
        invoices = await InvoiceService.list_invoices(
            session,
            from_date=from_date_parsed,
            to_date=to_date_parsed,
            limit=10000,
        )

        # Calculate totals
        total_invoiced = sum(inv.total for inv in invoices)
        total_paid = sum(inv.total for inv in invoices if inv.status == "paid")
        total_outstanding = sum(inv.total for inv in invoices if inv.status in ("sent", "overdue"))
        total_draft = sum(inv.total for inv in invoices if inv.status == "draft")
        total_overdue = sum(inv.total for inv in invoices if inv.status == "overdue")

        # Group by period
        by_period = defaultdict(lambda: {"invoiced": Decimal(0), "paid": Decimal(0), "count": 0})

        for inv in invoices:
            if group_by == "month":
                period = inv.issue_date.strftime("%Y-%m")
            elif group_by == "quarter":
                q = (inv.issue_date.month - 1) // 3 + 1
                period = f"{inv.issue_date.year}-Q{q}"
            else:
                period = str(inv.issue_date.year)

            by_period[period]["invoiced"] += inv.total
            by_period[period]["count"] += 1
            if inv.status == "paid":
                by_period[period]["paid"] += inv.total

        return {
            "period": f"{from_date_parsed} to {to_date_parsed}",
            "totals": {
                "invoiced": str(total_invoiced),
                "invoiced_formatted": format_currency(total_invoiced, "USD"),
                "paid": str(total_paid),
                "paid_formatted": format_currency(total_paid, "USD"),
                "outstanding": str(total_outstanding),
                "outstanding_formatted": format_currency(total_outstanding, "USD"),
                "draft": str(total_draft),
                "overdue": str(total_overdue),
                "invoice_count": len(invoices),
            },
            "by_period": {
                k: {
                    "invoiced": str(v["invoiced"]),
                    "paid": str(v["paid"]),
                    "count": v["count"],
                }
                for k, v in sorted(by_period.items())
            },
        }


@mcp.tool()
async def get_client_lifetime_value(
    client_id: Optional[int] = None,
    limit: int = 20,
) -> list:
    """
    Get lifetime value for clients.

    Args:
        client_id: Specific client ID (returns single client if provided)
        limit: Maximum clients to return (default 20, sorted by total paid)

    Returns:
        List of clients with their total invoiced, paid, and invoice counts
    """
    async with get_session() as session:
        if client_id:
            client = await ClientService.get_client(session, client_id)
            clients = [client] if client else []
        else:
            clients = await ClientService.list_clients(session)

        results = []
        for client in clients:
            if not client:
                continue

            invoices = await InvoiceService.list_invoices(
                session, client_id=client.id, limit=10000
            )

            total_invoiced = sum(inv.total for inv in invoices)
            total_paid = sum(inv.total for inv in invoices if inv.status == "paid")
            paid_invoices = [inv for inv in invoices if inv.status == "paid"]

            results.append({
                "client_id": client.id,
                "name": client.display_name,
                "email": client.email,
                "total_invoiced": str(total_invoiced),
                "total_invoiced_formatted": format_currency(total_invoiced, "USD"),
                "total_paid": str(total_paid),
                "total_paid_formatted": format_currency(total_paid, "USD"),
                "invoice_count": len(invoices),
                "paid_invoice_count": len(paid_invoices),
                "first_invoice": min(inv.issue_date for inv in invoices).isoformat() if invoices else None,
                "last_invoice": max(inv.issue_date for inv in invoices).isoformat() if invoices else None,
            })

        # Sort by total paid (descending) and limit
        results.sort(key=lambda x: Decimal(x["total_paid"]), reverse=True)
        return results[:limit]


@mcp.tool()
async def get_client_invoice_context(
    client_id: int,
    limit: int = 3,
) -> dict:
    """
    Get context for drafting a new invoice for a client.

    This provides recent invoice history to help draft invoices that match
    previous patterns (rates, descriptions, payment terms).

    Args:
        client_id: The client ID
        limit: Number of recent invoices to include (default 3)

    Returns:
        Client details, recent invoices with line items, and statistics
    """
    async with get_session() as session:
        client = await ClientService.get_client(session, client_id)
        if not client:
            return {"error": "Client not found"}

        # Get recent invoices
        invoices = await InvoiceService.list_invoices(
            session,
            client_id=client_id,
            limit=limit,
        )

        # Get all invoices for stats
        all_invoices = await InvoiceService.list_invoices(
            session,
            client_id=client_id,
            limit=10000,
        )

        total_billed = sum(inv.total for inv in all_invoices if inv.status in ("sent", "paid", "overdue"))
        paid_invoices = [inv for inv in all_invoices if inv.status == "paid"]
        total_paid = sum(inv.total for inv in paid_invoices)

        return {
            "client": {
                "id": client.id,
                "name": client.name,
                "business_name": client.business_name,
                "display_name": client.display_name,
                "email": client.email,
                "payment_terms_days": client.payment_terms_days,
            },
            "recent_invoices": [
                {
                    "invoice_number": inv.invoice_number,
                    "issue_date": inv.issue_date.isoformat(),
                    "total": str(inv.total),
                    "total_formatted": format_currency(inv.total, inv.currency_code),
                    "status": inv.status,
                    "currency_code": inv.currency_code,
                    "items": [
                        {
                            "description": item.description,
                            "quantity": item.quantity,
                            "unit_type": getattr(item, "unit_type", "qty"),
                            "unit_price": str(item.unit_price),
                            "total": str(item.total),
                        }
                        for item in inv.items
                    ],
                }
                for inv in invoices
            ],
            "statistics": {
                "total_billed": str(total_billed),
                "total_billed_formatted": format_currency(total_billed, "USD"),
                "total_paid": str(total_paid),
                "total_paid_formatted": format_currency(total_paid, "USD"),
                "invoice_count": len(all_invoices),
                "paid_count": len(paid_invoices),
                "average_invoice": str(total_billed / len(all_invoices)) if all_invoices else "0",
            },
        }


# ============================================================================
# Email Tools
# ============================================================================


@mcp.tool()
async def send_invoice_email(
    invoice_id: int,
    recipient_email: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
) -> dict:
    """
    Send an invoice PDF via email.

    Requires SMTP to be configured in business profile settings.

    Args:
        invoice_id: The invoice ID to send
        recipient_email: Override recipient (defaults to client's email)
        subject: Override email subject (defaults to "Invoice {number}")
        body: Override email body (defaults to friendly message with invoice details)

    Returns:
        Success status and details
    """
    from invoice_machine.email import EmailService
    from invoice_machine.pdf.generator import generate_pdf

    async with get_session() as session:
        # Get business profile for SMTP settings
        profile = await BusinessProfile.get_or_create(session)

        if not profile.smtp_enabled:
            return {
                "success": False,
                "error": "SMTP is not enabled. Configure SMTP settings in business profile first.",
            }

        # Get invoice
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            return {"success": False, "error": f"Invoice {invoice_id} not found"}

        # Generate PDF if needed
        if invoice.needs_pdf_regeneration:
            pdf_path = await generate_pdf(session, invoice)
            invoice.pdf_path = pdf_path
            invoice.pdf_generated_at = datetime.utcnow()
            await session.commit()

        # Send email
        email_service = EmailService(profile)
        result = await email_service.send_invoice(
            invoice,
            recipient_email=recipient_email,
            subject=subject,
            body=body,
        )

        # Update invoice status if sent successfully
        if result.get("success") and invoice.status == "draft":
            invoice.status = "sent"
            await session.commit()
            result["status_updated"] = "sent"

        return result


@mcp.tool()
async def test_smtp_connection() -> dict:
    """
    Test SMTP connection without sending an email.

    Returns:
        Success status and connection details
    """
    from invoice_machine.email import EmailService

    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        if not profile.smtp_enabled:
            return {
                "success": False,
                "error": "SMTP is not enabled. Configure SMTP settings first.",
            }

        email_service = EmailService(profile)
        return await email_service.test_connection()


@mcp.tool()
async def get_email_templates() -> dict:
    """
    Get the current email templates for invoice/quote emails.

    Returns:
        Current email subject and body templates, plus available placeholders.
    """
    from invoice_machine.email import DEFAULT_SUBJECT_TEMPLATE, DEFAULT_BODY_TEMPLATE

    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        return {
            "email_subject_template": profile.email_subject_template,
            "email_body_template": profile.email_body_template,
            "available_placeholders": [
                "{invoice_number}",
                "{quote_number}",
                "{document_type}",
                "{document_type_lower}",
                "{client_name}",
                "{client_business_name}",
                "{client_email}",
                "{total}",
                "{amount}",
                "{subtotal}",
                "{due_date}",
                "{issue_date}",
                "{your_name}",
                "{business_name}",
            ],
            "default_subject": DEFAULT_SUBJECT_TEMPLATE,
            "default_body": DEFAULT_BODY_TEMPLATE,
        }


@mcp.tool()
async def update_email_templates(
    email_subject_template: Optional[str] = None,
    email_body_template: Optional[str] = None,
) -> dict:
    """
    Update email templates for invoice/quote emails.

    Use placeholders like {invoice_number}, {client_name}, {total}, {due_date} etc.
    Set a template to empty string to clear it (will use defaults).

    Args:
        email_subject_template: Template for email subject
        email_body_template: Template for email body

    Returns:
        Updated email templates
    """
    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        if email_subject_template is not None:
            profile.email_subject_template = email_subject_template or None
        if email_body_template is not None:
            profile.email_body_template = email_body_template or None

        profile.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(profile)

        return {
            "email_subject_template": profile.email_subject_template,
            "email_body_template": profile.email_body_template,
        }


@mcp.tool()
async def preview_invoice_email(
    invoice_id: int,
    subject_template: Optional[str] = None,
    body_template: Optional[str] = None,
) -> dict:
    """
    Preview what an invoice email will look like with template expansion.

    Args:
        invoice_id: The invoice ID to preview email for
        subject_template: Optional override for subject template
        body_template: Optional override for body template

    Returns:
        Expanded subject, body, recipient email, and available placeholders
    """
    from invoice_machine.email import expand_template, DEFAULT_SUBJECT_TEMPLATE, DEFAULT_BODY_TEMPLATE

    async with get_session() as session:
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            return {"error": f"Invoice {invoice_id} not found"}

        profile = await BusinessProfile.get_or_create(session)

        # Use provided templates, fall back to saved templates, then defaults
        subj_tmpl = (
            subject_template
            if subject_template is not None
            else (profile.email_subject_template or DEFAULT_SUBJECT_TEMPLATE)
        )
        body_tmpl = (
            body_template
            if body_template is not None
            else (profile.email_body_template or DEFAULT_BODY_TEMPLATE)
        )

        subject = expand_template(subj_tmpl, invoice, profile)
        body = expand_template(body_tmpl, invoice, profile)

        return {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "recipient_email": invoice.client_email,
            "subject": subject,
            "body": body,
            "subject_template_used": subj_tmpl,
            "body_template_used": body_tmpl,
        }


# ============================================================================
# Search Tools
# ============================================================================


@mcp.tool()
async def search(
    query: str,
    search_invoices: bool = True,
    search_clients: bool = True,
    search_line_items: bool = True,
    limit: int = 20,
) -> dict:
    """
    Search across invoices, clients, and line items using full-text search.

    Supports partial matching and returns relevance-ranked results.

    Args:
        query: Search query (e.g., "acme", "consulting", "INV-2025")
        search_invoices: Include invoices in search (default: True)
        search_clients: Include clients in search (default: True)
        search_line_items: Include invoice line items in search (default: True)
        limit: Maximum results per category (default: 20)

    Returns:
        Dict with 'invoices', 'clients', and 'line_items' lists containing matching results
    """
    async with get_session() as session:
        return await SearchService.search(
            session,
            query=query,
            search_invoices=search_invoices,
            search_clients=search_clients,
            search_line_items=search_line_items,
            limit=limit,
        )


# ============================================================================
# Recurring Invoice Tools
# ============================================================================


@mcp.tool()
async def list_recurring_schedules(
    client_id: Optional[int] = None,
    include_paused: bool = False,
) -> list:
    """
    List recurring invoice schedules.

    Args:
        client_id: Filter by client ID
        include_paused: Include paused schedules (default: False, only active)

    Returns:
        List of recurring schedules with their details
    """
    import json

    async with get_session() as session:
        schedules = await RecurringService.list_schedules(
            session,
            client_id=client_id,
            active_only=not include_paused,
        )
        return [
            {
                "id": s.id,
                "client_id": s.client_id,
                "client_name": s.client.display_name if s.client else None,
                "name": s.name,
                "frequency": s.frequency,
                "schedule_day": s.schedule_day,
                "currency_code": s.currency_code,
                "payment_terms_days": s.payment_terms_days,
                "is_active": bool(s.is_active),
                "next_invoice_date": s.next_invoice_date.isoformat(),
                "last_invoice_id": s.last_invoice_id,
                "line_items": json.loads(s.line_items) if s.line_items else [],
                "tax_enabled": s.tax_enabled,
                "tax_rate": float(s.tax_rate) if s.tax_rate else None,
                "tax_name": s.tax_name,
            }
            for s in schedules
        ]


@mcp.tool()
async def get_recurring_schedule(schedule_id: int) -> Optional[dict]:
    """
    Get a recurring schedule by ID.

    Args:
        schedule_id: The schedule ID

    Returns:
        Schedule details or null if not found
    """
    import json

    async with get_session() as session:
        schedule = await RecurringService.get_schedule(session, schedule_id)
        if not schedule:
            return None

        return {
            "id": schedule.id,
            "client_id": schedule.client_id,
            "client_name": schedule.client.display_name if schedule.client else None,
            "name": schedule.name,
            "frequency": schedule.frequency,
            "schedule_day": schedule.schedule_day,
            "currency_code": schedule.currency_code,
            "payment_terms_days": schedule.payment_terms_days,
            "notes": schedule.notes,
            "is_active": bool(schedule.is_active),
            "next_invoice_date": schedule.next_invoice_date.isoformat(),
            "last_invoice_id": schedule.last_invoice_id,
            "line_items": json.loads(schedule.line_items) if schedule.line_items else [],
            "tax_enabled": schedule.tax_enabled,
            "tax_rate": float(schedule.tax_rate) if schedule.tax_rate else None,
            "tax_name": schedule.tax_name,
            "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
            "updated_at": schedule.updated_at.isoformat() if schedule.updated_at else None,
        }


@mcp.tool()
async def create_recurring_schedule(
    client_id: int,
    name: str,
    frequency: str,
    items: list,
    schedule_day: int = 1,
    currency_code: str = "USD",
    payment_terms_days: int = 30,
    notes: Optional[str] = None,
    next_invoice_date: Optional[str] = None,
    tax_enabled: Optional[int] = None,
    tax_rate: Optional[float] = None,
    tax_name: Optional[str] = None,
) -> dict:
    """
    Create a recurring invoice schedule.

    Args:
        client_id: Client ID for the recurring invoices
        name: Schedule name (e.g., "Monthly Retainer", "Quarterly Hosting")
        frequency: One of: daily, weekly, monthly, quarterly, yearly
        items: Line items: [{description, quantity, unit_price, unit_type}]
        schedule_day: Day of month (1-31) for monthly/quarterly/yearly,
                      or day of week (0=Mon, 6=Sun) for weekly
        currency_code: Currency code (default: USD)
        payment_terms_days: Payment terms in days (default: 30)
        notes: Invoice notes
        next_invoice_date: First invoice date (ISO format, defaults to next scheduled date)
        tax_enabled: Override tax setting (None = use client/global default)
        tax_rate: Override tax rate
        tax_name: Override tax name

    Returns:
        Created schedule details
    """
    from decimal import Decimal

    async with get_session() as session:
        # Parse next_invoice_date if provided
        parsed_date = None
        if next_invoice_date:
            parsed_date = date.fromisoformat(next_invoice_date)

        # Convert tax_rate to Decimal if provided
        tax_rate_decimal = Decimal(str(tax_rate)) if tax_rate is not None else None

        schedule = await RecurringService.create_schedule(
            session,
            client_id=client_id,
            name=name,
            frequency=frequency,
            schedule_day=schedule_day,
            currency_code=currency_code,
            payment_terms_days=payment_terms_days,
            notes=notes,
            line_items=items,
            next_invoice_date=parsed_date,
            tax_enabled=tax_enabled,
            tax_rate=tax_rate_decimal,
            tax_name=tax_name,
        )

        return {
            "id": schedule.id,
            "client_id": schedule.client_id,
            "name": schedule.name,
            "frequency": schedule.frequency,
            "next_invoice_date": schedule.next_invoice_date.isoformat(),
            "is_active": bool(schedule.is_active),
        }


@mcp.tool()
async def update_recurring_schedule(
    schedule_id: int,
    name: Optional[str] = None,
    frequency: Optional[str] = None,
    schedule_day: Optional[int] = None,
    currency_code: Optional[str] = None,
    payment_terms_days: Optional[int] = None,
    notes: Optional[str] = None,
    items: Optional[list] = None,
    next_invoice_date: Optional[str] = None,
    tax_enabled: Optional[int] = None,
    tax_rate: Optional[float] = None,
    tax_name: Optional[str] = None,
) -> Optional[dict]:
    """
    Update a recurring schedule.

    Only provide the fields you want to change.

    Args:
        schedule_id: The schedule ID
        name: Schedule name
        frequency: One of: daily, weekly, monthly, quarterly, yearly
        schedule_day: Day of month/week
        currency_code: Currency code
        payment_terms_days: Payment terms in days
        notes: Invoice notes
        items: Line items: [{description, quantity, unit_price, unit_type}]
        next_invoice_date: Next invoice date (ISO format)
        tax_enabled: Tax setting override
        tax_rate: Tax rate override
        tax_name: Tax name override

    Returns:
        Updated schedule or null if not found
    """
    from decimal import Decimal

    async with get_session() as session:
        updates = {}
        if name is not None:
            updates["name"] = name
        if frequency is not None:
            updates["frequency"] = frequency
        if schedule_day is not None:
            updates["schedule_day"] = schedule_day
        if currency_code is not None:
            updates["currency_code"] = currency_code
        if payment_terms_days is not None:
            updates["payment_terms_days"] = payment_terms_days
        if notes is not None:
            updates["notes"] = notes
        if items is not None:
            updates["line_items"] = items
        if next_invoice_date is not None:
            updates["next_invoice_date"] = date.fromisoformat(next_invoice_date)
        if tax_enabled is not None:
            updates["tax_enabled"] = tax_enabled
        if tax_rate is not None:
            updates["tax_rate"] = Decimal(str(tax_rate))
        if tax_name is not None:
            updates["tax_name"] = tax_name

        schedule = await RecurringService.update_schedule(session, schedule_id, **updates)
        if not schedule:
            return None

        return {
            "id": schedule.id,
            "name": schedule.name,
            "frequency": schedule.frequency,
            "next_invoice_date": schedule.next_invoice_date.isoformat(),
            "is_active": bool(schedule.is_active),
        }


@mcp.tool()
async def delete_recurring_schedule(schedule_id: int) -> bool:
    """
    Delete a recurring schedule.

    Args:
        schedule_id: The schedule ID

    Returns:
        True if deleted, False if not found
    """
    async with get_session() as session:
        return await RecurringService.delete_schedule(session, schedule_id)


@mcp.tool()
async def pause_recurring_schedule(schedule_id: int) -> bool:
    """
    Pause a recurring schedule.

    Paused schedules won't generate invoices until resumed.

    Args:
        schedule_id: The schedule ID

    Returns:
        True if paused, False if not found
    """
    async with get_session() as session:
        return await RecurringService.pause_schedule(session, schedule_id)


@mcp.tool()
async def resume_recurring_schedule(schedule_id: int) -> bool:
    """
    Resume a paused recurring schedule.

    Args:
        schedule_id: The schedule ID

    Returns:
        True if resumed, False if not found
    """
    async with get_session() as session:
        return await RecurringService.resume_schedule(session, schedule_id)


@mcp.tool()
async def trigger_recurring_schedule(schedule_id: int) -> dict:
    """
    Manually trigger a recurring schedule to create an invoice now.

    This creates an invoice immediately and updates the next scheduled date.

    Args:
        schedule_id: The schedule ID

    Returns:
        Result with invoice details or error
    """
    async with get_session() as session:
        return await RecurringService.trigger_schedule(session, schedule_id)


# Import for type references
import invoice_machine.database


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
        python -m invoice_machine.mcp.server --sse --port 8081
    """
    import asyncio
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.requests import Request
    from starlette.responses import Response
    from mcp.server.sse import SseServerTransport
    from invoice_machine.api.mcp import verify_mcp_auth, get_mcp_api_key_hash

    # Create SSE transport
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request):
        if not await verify_mcp_auth(request):
            return Response("Unauthorized", status_code=401)

        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp._mcp_server.run(
                streams[0], streams[1], mcp._mcp_server.create_initialization_options()
            )
        return Response()

    async def handle_messages(request: Request):
        if not await verify_mcp_auth(request):
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
    api_key_hash = asyncio.run(get_mcp_api_key_hash())
    if api_key_hash:
        print("API key authentication is ENABLED")
    else:
        print("WARNING: No MCP API key configured - connections will be rejected until one is generated.")
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
