"""Invoices API endpoints."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from invoicely.database import Invoice, InvoiceItem, get_session
from invoicely.services import InvoiceService

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


class InvoiceItemSchema(BaseModel):
    """Invoice item schema."""

    id: int
    description: str
    quantity: int
    unit_type: str = "qty"
    unit_price: str
    total: str
    sort_order: int

    class Config:
        from_attributes = True


class InvoiceSchema(BaseModel):
    """Invoice schema."""

    id: int
    invoice_number: str
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    client_business: Optional[str] = None
    client_address: Optional[str] = None
    client_email: Optional[str] = None
    status: str
    document_type: str = "invoice"
    client_reference: Optional[str] = None
    show_payment_instructions: bool = True
    selected_payment_methods: Optional[str] = None  # JSON array of method IDs
    issue_date: date
    due_date: Optional[date] = None
    payment_terms_days: int
    currency_code: str
    subtotal: str
    total: str
    notes: Optional[str] = None
    pdf_path: Optional[str] = None
    pdf_generated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    items: List[InvoiceItemSchema] = []

    class Config:
        from_attributes = True


class InvoiceItemCreate(BaseModel):
    """Invoice item creation schema."""

    description: str = Field(..., min_length=1, max_length=2000)
    quantity: int = Field(1, ge=1, le=10000)
    unit_type: str = Field("qty", pattern="^(qty|hours)$")
    unit_price: Decimal | str


class InvoiceCreate(BaseModel):
    """Invoice creation schema."""

    client_id: Optional[int] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    payment_terms_days: Optional[int] = Field(None, ge=0, le=365)
    currency_code: str = Field("USD", max_length=3)
    notes: Optional[str] = Field(None, max_length=10000)
    document_type: str = Field("invoice", pattern="^(invoice|quote)$")
    client_reference: Optional[str] = Field(None, max_length=100)
    show_payment_instructions: bool = True
    selected_payment_methods: Optional[str] = Field(None, max_length=1000)
    invoice_number_override: Optional[str] = Field(None, max_length=50)
    items: Optional[List[InvoiceItemCreate]] = Field(None, max_length=100)


class InvoiceUpdate(BaseModel):
    """Invoice update schema."""

    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    status: Optional[str] = Field(None, pattern="^(draft|sent|paid|overdue|cancelled)$")
    notes: Optional[str] = Field(None, max_length=10000)
    document_type: Optional[str] = Field(None, pattern="^(invoice|quote)$")
    client_reference: Optional[str] = Field(None, max_length=100)
    show_payment_instructions: Optional[bool] = None
    selected_payment_methods: Optional[str] = Field(None, max_length=1000)


class InvoiceItemUpdate(BaseModel):
    """Invoice item update schema."""

    description: Optional[str] = Field(None, max_length=2000)
    quantity: Optional[int] = Field(None, ge=1, le=10000)
    unit_type: Optional[str] = Field(None, pattern="^(qty|hours)$")
    unit_price: Optional[Decimal | str] = None
    sort_order: Optional[int] = Field(None, ge=0)


def _serialize_invoice(invoice: Invoice) -> dict:
    """Convert invoice to dict with proper decimal serialization."""
    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "client_id": invoice.client_id,
        "client_name": invoice.client_name,
        "client_business": invoice.client_business,
        "client_address": invoice.client_address,
        "client_email": invoice.client_email,
        "status": invoice.status,
        "document_type": invoice.document_type,
        "client_reference": invoice.client_reference,
        "show_payment_instructions": bool(invoice.show_payment_instructions),
        "selected_payment_methods": invoice.selected_payment_methods,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "payment_terms_days": invoice.payment_terms_days,
        "currency_code": invoice.currency_code,
        "subtotal": str(invoice.subtotal),
        "total": str(invoice.total),
        "notes": invoice.notes,
        "pdf_path": invoice.pdf_path,
        "pdf_generated_at": invoice.pdf_generated_at,
        "created_at": invoice.created_at,
        "updated_at": invoice.updated_at,
        "deleted_at": invoice.deleted_at,
        "items": [
            {
                "id": item.id,
                "description": item.description,
                "quantity": item.quantity,
                "unit_type": item.unit_type,
                "unit_price": str(item.unit_price),
                "total": str(item.total),
                "sort_order": item.sort_order,
            }
            for item in invoice.items
        ],
    }


@router.get("", response_model=List[InvoiceSchema])
async def list_invoices(
    status: Optional[str] = Query(None, description="Filter by status"),
    client_id: Optional[int] = Query(None, description="Filter by client ID"),
    from_date: Optional[date] = Query(None, description="Filter from this date"),
    to_date: Optional[date] = Query(None, description="Filter to this date"),
    include_deleted: bool = Query(False, description="Include soft-deleted invoices"),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> List[dict]:
    """List invoices with optional filters."""
    invoices = await InvoiceService.list_invoices(
        session,
        status=status,
        client_id=client_id,
        from_date=from_date,
        to_date=to_date,
        include_deleted=include_deleted,
        limit=limit,
    )
    return [_serialize_invoice(inv) for inv in invoices]


@router.post("", response_model=InvoiceSchema, status_code=201)
async def create_invoice(
    invoice_data: InvoiceCreate,
    session: AsyncSession = Depends(get_session),
) -> Invoice:
    """Create new invoice."""
    items_data = None
    if invoice_data.items:
        items_data = [
            {
                "description": item.description,
                "quantity": item.quantity,
                "unit_type": item.unit_type,
                "unit_price": Decimal(str(item.unit_price)),
            }
            for item in invoice_data.items
        ]

    invoice = await InvoiceService.create_invoice(
        session,
        client_id=invoice_data.client_id,
        issue_date=invoice_data.issue_date,
        due_date=invoice_data.due_date,
        payment_terms_days=invoice_data.payment_terms_days,
        currency_code=invoice_data.currency_code,
        notes=invoice_data.notes,
        document_type=invoice_data.document_type,
        client_reference=invoice_data.client_reference,
        show_payment_instructions=invoice_data.show_payment_instructions,
        selected_payment_methods=invoice_data.selected_payment_methods,
        invoice_number_override=invoice_data.invoice_number_override,
        items=items_data,
    )

    return _serialize_invoice(invoice)


@router.get("/{invoice_id}", response_model=InvoiceSchema)
async def get_invoice(
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get invoice by ID with items."""
    invoice = await InvoiceService.get_invoice(session, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return _serialize_invoice(invoice)


@router.put("/{invoice_id}", response_model=InvoiceSchema)
async def update_invoice(
    invoice_id: int,
    updates: InvoiceUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update invoice."""
    invoice = await InvoiceService.update_invoice(
        session,
        invoice_id,
        **updates.model_dump(exclude_unset=True),
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return _serialize_invoice(invoice)


@router.delete("/{invoice_id}", status_code=204)
async def delete_invoice(
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete invoice (soft delete)."""
    success = await InvoiceService.delete_invoice(session, invoice_id)
    if not success:
        raise HTTPException(status_code=404, detail="Invoice not found")


@router.post("/{invoice_id}/restore", response_model=InvoiceSchema)
async def restore_invoice(
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Restore deleted invoice."""
    success = await InvoiceService.restore_invoice(session, invoice_id)
    if not success:
        raise HTTPException(status_code=404, detail="Invoice not found or not deleted")

    invoice = await InvoiceService.get_invoice(session, invoice_id)
    return _serialize_invoice(invoice)


@router.post("/{invoice_id}/items", response_model=InvoiceItemSchema, status_code=201)
async def add_invoice_item(
    invoice_id: int,
    description: str = Query(..., description="Item description"),
    quantity: int = Query(1, ge=1, description="Quantity"),
    unit_price: Decimal | str = Query(..., description="Unit price"),
    sort_order: int = Query(0, description="Sort order"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Add line item to invoice."""
    item = await InvoiceService.add_item(
        session, invoice_id, description, quantity, unit_price, sort_order
    )
    return {
        "id": item.id,
        "description": item.description,
        "quantity": item.quantity,
        "unit_price": str(item.unit_price),
        "total": str(item.total),
        "sort_order": item.sort_order,
    }


@router.put("/{invoice_id}/items/{item_id}", response_model=InvoiceItemSchema)
async def update_invoice_item(
    invoice_id: int,
    item_id: int,
    updates: InvoiceItemUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update line item."""
    item = await InvoiceService.update_item(
        session, item_id, **updates.model_dump(exclude_unset=True)
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {
        "id": item.id,
        "description": item.description,
        "quantity": item.quantity,
        "unit_price": str(item.unit_price),
        "total": str(item.total),
        "sort_order": item.sort_order,
    }


@router.delete("/{invoice_id}/items/{item_id}", status_code=204)
async def delete_invoice_item(
    invoice_id: int,
    item_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Remove line item."""
    success = await InvoiceService.remove_item(session, item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found")


@router.post("/{invoice_id}/generate-pdf")
async def generate_invoice_pdf(
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Generate PDF for invoice."""
    from invoicely.pdf.generator import generate_pdf
    from invoicely.config import get_settings

    settings = get_settings()
    invoice = await InvoiceService.get_invoice(session, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Generate PDF
    pdf_path = await generate_pdf(session, invoice)

    # Update invoice
    from datetime import datetime

    invoice.pdf_path = pdf_path
    invoice.pdf_generated_at = datetime.utcnow()
    await session.commit()

    return {
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "pdf_url": f"{settings.app_base_url}/api/invoices/{invoice.id}/pdf",
        "generated_at": invoice.pdf_generated_at.isoformat(),
    }


@router.get("/{invoice_id}/pdf")
async def get_invoice_pdf(
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get generated PDF for invoice, generating if needed."""
    from fastapi.responses import FileResponse
    from invoicely.config import get_settings
    from invoicely.pdf.generator import generate_pdf

    settings = get_settings()
    invoice = await InvoiceService.get_invoice(session, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Check if PDF needs to be generated
    needs_generation = (
        not invoice.pdf_path
        or not invoice.pdf_generated_at
        or invoice.updated_at > invoice.pdf_generated_at
    )

    if needs_generation:
        # Generate PDF
        pdf_path = await generate_pdf(session, invoice)
        invoice.pdf_path = pdf_path
        invoice.pdf_generated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(invoice)

    # Sanitize pdf_path to prevent path traversal
    if not all(c.isalnum() or c in "._-/" for c in invoice.pdf_path):
        raise HTTPException(status_code=400, detail="Invalid PDF path")

    # Resolve path and ensure it's within data directory
    pdf_path = (settings.data_dir / invoice.pdf_path).resolve()

    if not str(pdf_path).startswith(str(settings.data_dir.resolve())):
        raise HTTPException(status_code=404, detail="PDF not found")

    if not pdf_path.exists() or not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="PDF file not found")

    # Build filename: "Client Company - Invoice#.pdf" or just "Invoice#.pdf"
    client_part = ""
    if invoice.client_business:
        # Sanitize client name for filename
        safe_client = "".join(c for c in invoice.client_business if c.isalnum() or c in " -_")
        safe_client = safe_client.strip()
        if safe_client:
            client_part = f"{safe_client} - "

    filename = f"{client_part}{invoice.invoice_number}.pdf"

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=filename,
    )
