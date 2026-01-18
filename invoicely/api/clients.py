"""Clients API endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from invoicely.database import Client, get_session
from invoicely.services import ClientService
from invoicely.rate_limit import limiter

router = APIRouter(prefix="/api/clients", tags=["clients"])


class ClientSchema(BaseModel):
    """Client schema."""

    id: int
    name: Optional[str] = None
    business_name: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    payment_terms_days: int = 30
    notes: Optional[str] = None
    # Tax settings (null = use global default)
    tax_enabled: Optional[int] = None
    tax_rate: Optional[str] = None
    tax_name: Optional[str] = None
    # Currency preference (null = use global default)
    preferred_currency: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ClientCreate(BaseModel):
    """Client creation schema."""

    name: Optional[str] = Field(None, max_length=255)
    business_name: Optional[str] = Field(None, max_length=255)
    address_line1: Optional[str] = Field(None, max_length=500)
    address_line2: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    payment_terms_days: int = Field(30, ge=0, le=365)
    notes: Optional[str] = Field(None, max_length=10000)
    # Tax settings (null = use global default)
    tax_enabled: Optional[int] = Field(None, ge=0, le=1)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    tax_name: Optional[str] = Field(None, max_length=50)
    # Currency preference (null = use global default)
    preferred_currency: Optional[str] = Field(None, max_length=3)


class ClientUpdate(BaseModel):
    """Client update schema."""

    name: Optional[str] = Field(None, max_length=255)
    business_name: Optional[str] = Field(None, max_length=255)
    address_line1: Optional[str] = Field(None, max_length=500)
    address_line2: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    payment_terms_days: Optional[int] = Field(None, ge=0, le=365)
    notes: Optional[str] = Field(None, max_length=10000)
    # Tax settings (null = use global default)
    tax_enabled: Optional[int] = Field(None, ge=0, le=1)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    tax_name: Optional[str] = Field(None, max_length=50)
    # Currency preference (null = use global default)
    preferred_currency: Optional[str] = Field(None, max_length=3)


@router.get("", response_model=List[ClientSchema])
@limiter.limit("120/minute")
async def list_clients(
    request: Request,
    search: Optional[str] = Query(None, description="Search by name or business name"),
    include_deleted: bool = Query(False, description="Include soft-deleted clients"),
    session: AsyncSession = Depends(get_session),
) -> List[Client]:
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
