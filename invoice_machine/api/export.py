"""CSV export endpoints for accounting/tax-time workflows."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.service.export import EXPORT_KINDS, export_csv
from invoice_machine.utils import utc_now

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/{kind}.csv")
@limiter.limit("20/minute")
async def export_kind_csv(
    request: Request,
    kind: str,
    from_date: date | None = Query(None, description="Filter from this date (inclusive)"),
    to_date: date | None = Query(None, description="Filter to this date (inclusive)"),
    include_deleted: bool = Query(False, description="Include trashed records"),
    document_type: str | None = Query(
        None, pattern="^(invoice|quote)$", description="Restrict to invoices or quotes"
    ),
    session: AsyncSession = Depends(get_session),
):
    """Stream a CSV export of invoices, line_items, payments, or clients."""
    if kind not in EXPORT_KINDS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown export. Available: {', '.join(EXPORT_KINDS)}",
        )

    rows = export_csv(
        session,
        kind,
        from_date=from_date,
        to_date=to_date,
        include_deleted=include_deleted,
        document_type=document_type,
    )

    filename = f"{kind}-{utc_now().date().isoformat()}.csv"
    return StreamingResponse(
        rows,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # The body is generated per request; never let a proxy cache financials.
            "Cache-Control": "no-store",
        },
    )
