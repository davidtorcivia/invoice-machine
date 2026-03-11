"""Clients API endpoints."""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import Client, get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.services import ClientService

router = APIRouter(prefix="/api/clients", tags=["clients"])


class ClientSchema(BaseModel):
    """Client schema."""

    id: int
    name: str | None = None
    business_name: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    email: str | None = None
    phone: str | None = None
    payment_terms_days: int = 30
    notes: str | None = None
    # Tax settings (null = use global default)
    tax_enabled: int | None = None
    tax_rate: str | None = None
    tax_name: str | None = None
    # Currency preference (null = use global default)
    preferred_currency: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ClientCreate(BaseModel):
    """Client creation schema."""

    name: str | None = Field(None, max_length=255)
    business_name: str | None = Field(None, max_length=255)
    address_line1: str | None = Field(None, max_length=500)
    address_line2: str | None = Field(None, max_length=500)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    country: str | None = Field(None, max_length=100)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    payment_terms_days: int = Field(30, ge=0, le=365)
    notes: str | None = Field(None, max_length=10000)
    # Tax settings (null = use global default)
    tax_enabled: int | None = Field(None, ge=0, le=1)
    tax_rate: Decimal | None = Field(None, ge=0, le=100)
    tax_name: str | None = Field(None, max_length=50)
    # Currency preference (null = use global default)
    preferred_currency: str | None = Field(None, max_length=3)


class ClientUpdate(BaseModel):
    """Client update schema."""

    name: str | None = Field(None, max_length=255)
    business_name: str | None = Field(None, max_length=255)
    address_line1: str | None = Field(None, max_length=500)
    address_line2: str | None = Field(None, max_length=500)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    country: str | None = Field(None, max_length=100)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    payment_terms_days: int | None = Field(None, ge=0, le=365)
    notes: str | None = Field(None, max_length=10000)
    # Tax settings (null = use global default)
    tax_enabled: int | None = Field(None, ge=0, le=1)
    tax_rate: Decimal | None = Field(None, ge=0, le=100)
    tax_name: str | None = Field(None, max_length=50)
    # Currency preference (null = use global default)
    preferred_currency: str | None = Field(None, max_length=3)


@router.get("", response_model=list[ClientSchema])
@limiter.limit("120/minute")
async def list_clients(
    request: Request,
    search: str | None = Query(None, description="Search by name or business name"),
    include_deleted: bool = Query(False, description="Include soft-deleted clients"),
    session: AsyncSession = Depends(get_session),
) -> list[Client]:
    """List all clients."""
    return await ClientService.list_clients(
        session, search=search, include_deleted=include_deleted
    )


@router.post("", response_model=ClientSchema, status_code=201)
@limiter.limit("30/hour")
async def create_client(
    request: Request,
    client_data: ClientCreate,
    session: AsyncSession = Depends(get_session),
) -> Client:
    """Create new client."""
    return await ClientService.create_client(session, **client_data.model_dump())


@router.get("/{client_id}", response_model=ClientSchema)
@limiter.limit("120/minute")
async def get_client(
    request: Request,
    client_id: int,
    session: AsyncSession = Depends(get_session),
) -> Client:
    """Get client by ID."""
    client = await ClientService.get_client(session, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.put("/{client_id}", response_model=ClientSchema)
@limiter.limit("60/hour")
async def update_client(
    request: Request,
    client_id: int,
    updates: ClientUpdate,
    session: AsyncSession = Depends(get_session),
) -> Client:
    """Update client."""
    client = await ClientService.update_client(
        session, client_id, **updates.model_dump(exclude_unset=True)
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.delete("/{client_id}", status_code=204)
@limiter.limit("30/hour")
async def delete_client(
    request: Request,
    client_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete client (soft delete)."""
    success = await ClientService.delete_client(session, client_id)
    if not success:
        raise HTTPException(status_code=404, detail="Client not found")


@router.post("/{client_id}/restore", response_model=ClientSchema)
@limiter.limit("30/hour")
async def restore_client(
    request: Request,
    client_id: int,
    session: AsyncSession = Depends(get_session),
) -> Client:
    """Restore deleted client."""
    success = await ClientService.restore_client(session, client_id)
    if not success:
        raise HTTPException(status_code=404, detail="Client not found or not deleted")

    # Get the restored client
    client = await ClientService.get_client(session, client_id)
    return client
