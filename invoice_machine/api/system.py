"""Operator status: version, scheduler ownership, and background job outcomes."""

from fastapi import APIRouter, Request

from invoice_machine import __version__
from invoice_machine.config import get_settings
from invoice_machine.rate_limit import limiter
from invoice_machine.utils import ensure_utc, utc_now

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
@limiter.limit("60/minute")
async def system_status(request: Request) -> dict:
    """Version, environment, uptime, and the last outcome of every background job."""
    state = request.app.state
    started = ensure_utc(getattr(state, "started_at", None))
    return {
        "version": __version__,
        "environment": get_settings().environment,
        "uptime_seconds": round((utc_now() - started).total_seconds()) if started else None,
        "scheduler": {
            "active": bool(getattr(state, "scheduler_active", False)),
            "jobs": getattr(state, "jobs", {}),
        },
    }
