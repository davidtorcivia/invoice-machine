"""Shared serializers for API, MCP, and frontend-facing payloads."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from invoice_machine.database import (
    BusinessProfile,
    Client,
    Invoice,
    InvoiceItem,
    RecurringSchedule,
)
from invoice_machine.service.common import format_quantity


def _maybe_iso(value: Any, json_ready: bool) -> Any:
    """Convert date-like values to ISO strings for JSON-safe payloads."""
    if json_ready and isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def parse_json_list(value: Any) -> list:
    """Parse a JSON-backed list field safely."""
    if isinstance(value, list):
        return value
    if not value:
        return []

    import json

    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def dump_json_list(values: list | None) -> str | None:
    """Serialize a list field or return None for empty values."""
    if not values:
        return None

    import json

    return json.dumps(values)


def serialize_invoice_item(item: InvoiceItem) -> dict:
    """Serialize an invoice item."""
    return {
        "id": item.id,
        "description": item.description,
        "quantity": format_quantity(item.quantity),
        "unit_type": getattr(item, "unit_type", "qty"),
        "unit_price": str(item.unit_price),
        "total": str(item.total),
        "sort_order": getattr(item, "sort_order", 0),
    }


def build_line_items_preview(
    invoice: Invoice,
    max_items: int = 2,
    max_len: int = 120,
) -> str:
    """Build compact preview text from invoice line item descriptions."""
    descriptions = [
        (item.description or "").strip()
        for item in invoice.items
        if (item.description or "").strip()
    ]
    if not descriptions:
        return ""

    preview = ", ".join(descriptions[:max_items])
    if len(descriptions) > max_items:
        preview = f"{preview} +{len(descriptions) - max_items} more"

    if len(preview) > max_len:
        return preview[: max_len - 3].rstrip() + "..."
    return preview


def serialize_client(client: Client, *, json_ready: bool = False) -> dict:
    """Serialize a client for API or MCP responses."""
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
        "tax_rate": (
            float(client.tax_rate) if json_ready and client.tax_rate is not None else client.tax_rate
        ),
        "tax_name": client.tax_name,
        "preferred_currency": client.preferred_currency,
        "is_active": client.is_active,
        "created_at": _maybe_iso(client.created_at, json_ready),
        "updated_at": _maybe_iso(client.updated_at, json_ready),
        "deleted_at": _maybe_iso(client.deleted_at, json_ready),
    }


def serialize_business_profile(
    profile: BusinessProfile,
    *,
    json_ready: bool = False,
    payment_methods_as_list: bool = False,
) -> dict:
    """Serialize business profile fields shared across API and MCP."""
    payment_methods = (
        profile.payment_methods_list if payment_methods_as_list else profile.payment_methods
    )
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
        "default_currency_code": profile.default_currency_code,
        "default_notes": profile.default_notes,
        "default_payment_instructions": profile.default_payment_instructions,
        "payment_methods": payment_methods,
        "theme_preference": profile.theme_preference,
        "mcp_api_key_configured": profile.mcp_api_key_configured,
        "bot_api_key_configured": profile.bot_api_key_configured,
        "app_base_url": profile.app_base_url,
        "default_tax_enabled": bool(getattr(profile, "default_tax_enabled", 0)),
        "default_tax_rate": (
            str(getattr(profile, "default_tax_rate", 0))
            if getattr(profile, "default_tax_rate", None) is not None
            else None
        ),
        "default_tax_name": getattr(profile, "default_tax_name", "Tax"),
        "smtp_enabled": bool(getattr(profile, "smtp_enabled", 0)),
        "smtp_host": getattr(profile, "smtp_host", None),
        "smtp_port": getattr(profile, "smtp_port", 587),
        "smtp_username": getattr(profile, "smtp_username", None),
        "smtp_password_set": bool(getattr(profile, "smtp_password", None)),
        "smtp_from_email": getattr(profile, "smtp_from_email", None),
        "smtp_from_name": getattr(profile, "smtp_from_name", None),
        "smtp_use_tls": bool(getattr(profile, "smtp_use_tls", 1)),
        "email_subject_template": getattr(profile, "email_subject_template", None),
        "email_body_template": getattr(profile, "email_body_template", None),
        "created_at": _maybe_iso(profile.created_at, json_ready),
        "updated_at": _maybe_iso(profile.updated_at, json_ready),
    }


def serialize_invoice(
    invoice: Invoice,
    *,
    include_items: bool = True,
    include_preview: bool = True,
    include_formatted_total: bool = False,
    json_ready: bool = False,
    selected_payment_methods_as_list: bool = False,
) -> dict:
    """Serialize invoice fields for API or MCP responses."""
    selected_payment_methods: Any = (
        invoice.selected_payment_methods_list
        if selected_payment_methods_as_list
        else invoice.selected_payment_methods
    )
    line_items_count = len(invoice.items)

    data = {
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
        "issue_date": _maybe_iso(invoice.issue_date, json_ready),
        "due_date": _maybe_iso(invoice.due_date, json_ready),
        "payment_terms_days": invoice.payment_terms_days,
        "currency_code": invoice.currency_code,
        "subtotal": str(invoice.subtotal),
        "tax_enabled": bool(getattr(invoice, "tax_enabled", 0)),
        "tax_rate": str(getattr(invoice, "tax_rate", 0)) if getattr(invoice, "tax_rate", None) else "0",
        "tax_name": getattr(invoice, "tax_name", "Tax") or "Tax",
        "tax_amount": (
            str(getattr(invoice, "tax_amount", 0))
            if getattr(invoice, "tax_amount", None) is not None
            else "0"
        ),
        "total": str(invoice.total),
        "notes": invoice.notes,
        "show_payment_instructions": bool(getattr(invoice, "show_payment_instructions", True)),
        "selected_payment_methods": selected_payment_methods,
        "pdf_path": invoice.pdf_path,
        "pdf_generated_at": _maybe_iso(invoice.pdf_generated_at, json_ready),
        "created_at": _maybe_iso(invoice.created_at, json_ready),
        "updated_at": _maybe_iso(invoice.updated_at, json_ready),
        "deleted_at": _maybe_iso(invoice.deleted_at, json_ready),
        "line_items_count": line_items_count,
    }
    if include_preview:
        data["line_items_preview"] = build_line_items_preview(invoice)
    if include_items:
        data["items"] = [serialize_invoice_item(item) for item in invoice.items]
    else:
        data["items"] = []
    if include_formatted_total:
        from invoice_machine.services import format_currency

        total_amount = Decimal(str(invoice.total))
        data["total_formatted"] = format_currency(total_amount, invoice.currency_code)
    return data


def serialize_recurring_schedule(
    schedule: RecurringSchedule,
    *,
    json_ready: bool = False,
) -> dict:
    """Serialize recurring schedule fields for API or MCP responses."""
    return {
        "id": schedule.id,
        "client_id": schedule.client_id,
        "client_name": schedule.client.name if schedule.client else None,
        "client_business": schedule.client.business_name if schedule.client else None,
        "name": schedule.name,
        "frequency": schedule.frequency,
        "schedule_day": schedule.schedule_day,
        "currency_code": schedule.currency_code,
        "payment_terms_days": schedule.payment_terms_days,
        "notes": schedule.notes,
        "line_items": schedule.line_items_list,
        "tax_enabled": bool(schedule.tax_enabled) if schedule.tax_enabled is not None else None,
        "tax_rate": (
            str(schedule.tax_rate)
            if schedule.tax_rate is not None and not json_ready
            else (float(schedule.tax_rate) if schedule.tax_rate is not None else None)
        ),
        "tax_name": schedule.tax_name,
        "is_active": bool(schedule.is_active),
        "next_invoice_date": _maybe_iso(schedule.next_invoice_date, json_ready),
        "last_invoice_id": schedule.last_invoice_id,
        "created_at": _maybe_iso(schedule.created_at, json_ready),
        "updated_at": _maybe_iso(schedule.updated_at, json_ready),
    }
