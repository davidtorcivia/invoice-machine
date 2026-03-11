"""Invoices API endpoints."""

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.api.schemas import LineItemCreate
from invoice_machine.database import Invoice, get_session
from invoice_machine.presenters import serialize_invoice, serialize_invoice_item
from invoice_machine.services import InvoiceService
from invoice_machine.utils import (
    INVOICE_NUMBER_REGEX,
    ensure_utc,
    sanitize_filename_component,
    utc_now,
)

router = APIRouter(prefix="/api/invoices", tags=["invoices"])
limiter = Limiter(key_func=get_remote_address)


class InvoiceItemSchema(BaseModel):
    """Invoice item schema."""

    id: int
    description: str
    quantity: int
    unit_type: str = "qty"
    unit_price: str
    total: str
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class InvoiceSchema(BaseModel):
    """Invoice schema."""

    id: int
    invoice_number: str
    client_id: int | None = None
    client_name: str | None = None
    client_business: str | None = None
    client_address: str | None = None
    client_email: str | None = None
    status: str
    document_type: str = "invoice"
    client_reference: str | None = None
    show_payment_instructions: bool = True
    selected_payment_methods: str | None = None  # JSON array of method IDs
    issue_date: date
    due_date: date | None = None
    payment_terms_days: int
    currency_code: str
    subtotal: str
    total: str
    tax_enabled: bool = False
    tax_rate: str = "0"
    tax_name: str = "Tax"
    tax_amount: str = "0"
    notes: str | None = None
    pdf_path: str | None = None
    pdf_generated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    line_items_count: int = 0
    line_items_preview: str = ""
    items: list[InvoiceItemSchema] = []

    model_config = ConfigDict(from_attributes=True)


class InvoiceCreate(BaseModel):
    """Invoice creation schema."""

    client_id: int | None = None
    issue_date: date | None = None
    due_date: date | None = None
    payment_terms_days: int | None = Field(None, ge=0, le=365)
    currency_code: str = Field("USD", max_length=3)
    notes: str | None = Field(None, max_length=10000)
    document_type: str = Field("invoice", pattern="^(invoice|quote)$")
    client_reference: str | None = Field(None, max_length=100)
    show_payment_instructions: bool = True
    selected_payment_methods: str | None = Field(None, max_length=1000)
    invoice_number_override: str | None = Field(
        None, max_length=50, pattern=INVOICE_NUMBER_REGEX
    )
    # Tax settings
    tax_enabled: int | None = Field(0, ge=0, le=1)
    tax_rate: Decimal | None = Field(None, ge=0, le=100)
    tax_name: str | None = Field(None, max_length=50)
    items: list[LineItemCreate] | None = Field(None, max_length=100)


class InvoiceUpdate(BaseModel):
    """Invoice update schema."""

    issue_date: date | None = None
    due_date: date | None = None
    status: str | None = Field(None, pattern="^(draft|sent|paid|overdue|cancelled)$")
    notes: str | None = Field(None, max_length=10000)
    document_type: str | None = Field(None, pattern="^(invoice|quote)$")
    client_reference: str | None = Field(None, max_length=100)
    show_payment_instructions: bool | None = None
    selected_payment_methods: str | None = Field(None, max_length=1000)
    # Tax settings
    tax_enabled: int | None = Field(None, ge=0, le=1)
    tax_rate: Decimal | None = Field(None, ge=0, le=100)
    tax_name: str | None = Field(None, max_length=50)


class InvoiceItemUpdate(BaseModel):
    """Invoice item update schema."""

    description: str | None = Field(None, max_length=2000)
    quantity: int | None = Field(None, ge=1, le=10000)
    unit_type: str | None = Field(None, pattern="^(qty|hours)$")
    unit_price: Decimal | str | None = None
    sort_order: int | None = Field(None, ge=0)


class BulkActionError(BaseModel):
    """Error details for a single invoice in bulk action."""

    id: int
    reason: str


class BulkActionRequest(BaseModel):
    """Bulk action request schema."""

    action: str = Field(..., pattern="^(mark_sent|mark_paid|delete)$")
    invoice_ids: list[int] = Field(..., min_length=1, max_length=100)


class BulkActionResponse(BaseModel):
    """Bulk action response schema."""

    action: str
    total_requested: int
    successful: int
    failed: int
    errors: list[BulkActionError] = []


class InvoicePagination(BaseModel):
    """Pagination metadata for invoice list responses."""

    page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PaginatedInvoiceResponse(BaseModel):
    """Paginated invoice list response."""

    items: list[InvoiceSchema]
    pagination: InvoicePagination


@router.get("", response_model=list[InvoiceSchema])
@limiter.limit("120/minute")
async def list_invoices(
    request: Request,
    status: str | None = Query(None, description="Filter by status"),
    document_type: str | None = Query(
        None, pattern="^(invoice|quote)$", description="Filter by document type"
    ),
    client_id: int | None = Query(None, description="Filter by client ID"),
    from_date: date | None = Query(None, description="Filter from this date"),
    to_date: date | None = Query(None, description="Filter to this date"),
    include_deleted: bool = Query(False, description="Include soft-deleted invoices"),
    sort_by: str = Query(
        "created_at",
        pattern="^(created_at|issue_date|due_date|client|invoice_number|total|status)$",
    ),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """List invoices with optional filters."""
    invoices = await InvoiceService.list_invoices(
        session,
        status=status,
        document_type=document_type,
        client_id=client_id,
        from_date=from_date,
        to_date=to_date,
        include_deleted=include_deleted,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
    )
    return [serialize_invoice(inv, include_items=False) for inv in invoices]


@router.get("/paginated", response_model=PaginatedInvoiceResponse)
@limiter.limit("120/minute")
async def list_invoices_paginated(
    request: Request,
    status: str | None = Query(None, description="Filter by status"),
    document_type: str | None = Query(
        None, pattern="^(invoice|quote)$", description="Filter by document type"
    ),
    client_id: int | None = Query(None, description="Filter by client ID"),
    from_date: date | None = Query(None, description="Filter from this date"),
    to_date: date | None = Query(None, description="Filter to this date"),
    include_deleted: bool = Query(False, description="Include soft-deleted invoices"),
    sort_by: str = Query(
        "created_at",
        pattern="^(created_at|issue_date|due_date|client|invoice_number|total|status)$",
    ),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """List invoices with pagination metadata."""
    items, total = await InvoiceService.list_invoices_paginated(
        session,
        status=status,
        document_type=document_type,
        client_id=client_id,
        from_date=from_date,
        to_date=to_date,
        include_deleted=include_deleted,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        per_page=per_page,
    )

    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    return {
        "items": [serialize_invoice(inv, include_items=False) for inv in items],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }


@router.post("/bulk", response_model=BulkActionResponse)
@limiter.limit("30/minute")
async def bulk_action(
    request: Request,
    action_data: BulkActionRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Execute bulk action on multiple invoices."""
    result = await InvoiceService.bulk_action(
        session,
        action=action_data.action,
        invoice_ids=action_data.invoice_ids,
    )
    return result


@router.post("", response_model=InvoiceSchema, status_code=201)
@limiter.limit("60/hour")
async def create_invoice(
    request: Request,
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

    try:
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
            tax_enabled=invoice_data.tax_enabled,
            tax_rate=invoice_data.tax_rate,
            tax_name=invoice_data.tax_name,
            items=items_data,
        )
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return serialize_invoice(invoice)


@router.get("/{invoice_id}", response_model=InvoiceSchema)
async def get_invoice(
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get invoice by ID with items."""
    invoice = await InvoiceService.get_invoice(session, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return serialize_invoice(invoice)


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
    return serialize_invoice(invoice)


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
    return serialize_invoice(invoice)


@router.post("/{invoice_id}/items", response_model=InvoiceItemSchema, status_code=201)
async def add_invoice_item(
    invoice_id: int,
    description: str = Query(..., description="Item description"),
    quantity: int = Query(1, ge=1, description="Quantity"),
    unit_type: str = Query("qty", pattern="^(qty|hours)$", description="Unit type"),
    unit_price: Decimal | str = Query(..., description="Unit price"),
    sort_order: int = Query(0, description="Sort order"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Add line item to invoice."""
    try:
        item = await InvoiceService.add_item(
            session,
            invoice_id,
            description,
            quantity,
            unit_price,
            sort_order,
            unit_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        **serialize_invoice_item(item),
    }


@router.put("/{invoice_id}/items/{item_id}", response_model=InvoiceItemSchema)
async def update_invoice_item(
    invoice_id: int,
    item_id: int,
    updates: InvoiceItemUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update line item."""
    try:
        item = await InvoiceService.update_item(
            session, item_id, invoice_id=invoice_id, **updates.model_dump(exclude_unset=True)
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {
        **serialize_invoice_item(item),
    }


@router.delete("/{invoice_id}/items/{item_id}", status_code=204)
async def delete_invoice_item(
    invoice_id: int,
    item_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Remove line item."""
    try:
        success = await InvoiceService.remove_item(session, item_id, invoice_id=invoice_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not success:
        raise HTTPException(status_code=404, detail="Item not found")


@router.post("/{invoice_id}/generate-pdf")
@limiter.limit("30/hour")
async def generate_invoice_pdf(
    request: Request,
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Generate PDF for invoice."""
    from invoice_machine.config import get_settings
    from invoice_machine.pdf.generator import generate_pdf

    settings = get_settings()
    invoice = await InvoiceService.get_invoice(session, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Generate PDF
    pdf_path = await generate_pdf(session, invoice)

    # Update invoice
    invoice.pdf_path = pdf_path
    invoice.pdf_generated_at = utc_now()
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

    from invoice_machine.config import get_settings
    from invoice_machine.pdf.generator import generate_pdf

    settings = get_settings()
    invoice = await InvoiceService.get_invoice(session, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Check if PDF needs to be generated
    needs_generation = (
        not invoice.pdf_path
        or not invoice.pdf_generated_at
        or ensure_utc(invoice.updated_at) > ensure_utc(invoice.pdf_generated_at)
    )

    if needs_generation:
        # Generate PDF
        pdf_path = await generate_pdf(session, invoice)
        invoice.pdf_path = pdf_path
        invoice.pdf_generated_at = utc_now()
        await session.commit()
        await session.refresh(invoice)

    # Sanitize pdf_path to prevent path traversal
    # Reject any path traversal attempts
    if not invoice.pdf_path or ".." in invoice.pdf_path:
        raise HTTPException(status_code=400, detail="Invalid PDF path")

    # Extract just the filename (basename) to prevent directory traversal
    # PDF paths are stored as "pdfs/{filename}.pdf"
    import os
    safe_filename = os.path.basename(invoice.pdf_path)

    # Validate filename contains only safe characters
    if not safe_filename or not all(c.isalnum() or c in "._-" for c in safe_filename):
        raise HTTPException(status_code=400, detail="Invalid PDF path")

    # Build the path - PDFs are always stored in the pdfs subdirectory
    pdf_path = (settings.data_dir / "pdfs" / safe_filename).resolve()
    data_dir_resolved = settings.data_dir.resolve()

    # Final security check: ensure resolved path is within data directory
    if not str(pdf_path).startswith(str(data_dir_resolved) + os.sep):
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

    safe_invoice_number = sanitize_filename_component(
        invoice.invoice_number, f"invoice-{invoice.id}"
    )
    filename = f"{client_part}{safe_invoice_number}.pdf"

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=filename,
    )
