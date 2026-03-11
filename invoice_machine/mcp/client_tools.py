"""Client MCP tools."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from invoice_machine.database import Client
from invoice_machine.presenters import serialize_client
from invoice_machine.services import ClientService
from invoice_machine.utils import utc_now

from .context import get_session, mcp

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
        return [serialize_client(client, json_ready=True) for client in clients]


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
        return serialize_client(client, json_ready=True)


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

        return serialize_client(client, json_ready=True)


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
        return serialize_client(client, json_ready=True)


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

