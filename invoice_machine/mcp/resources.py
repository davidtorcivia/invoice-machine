"""MCP resources: addressable, read-only views of invoices and clients.

URIs use the human-facing identifier where one exists: invoices are addressed by
their number (`20250115-1`), not their database ID. Clients have no such
identifier, so they are addressed by ID.
"""

from __future__ import annotations

import json

from sqlalchemy import select

from invoice_machine.database import BusinessProfile, Invoice
from invoice_machine.presenters import (
    serialize_business_profile,
    serialize_client,
    serialize_invoice,
)
from invoice_machine.service.clients import ClientService

from .context import get_session, mcp

_JSON = "application/json"


def _dump(payload) -> str:
    return json.dumps(payload, indent=2, default=str)


@mcp.resource(
    "invoice://{invoice_number}",
    name="Invoice",
    title="Invoice by number",
    description=(
        "A single invoice or quote addressed by its invoice number "
        "(e.g. invoice://20250115-1), including line items and payment status."
    ),
    mime_type=_JSON,
)
async def invoice_resource(invoice_number: str) -> str:
    """Read one invoice by its human-facing number."""
    async with get_session() as session:
        result = await session.execute(
            select(Invoice).where(Invoice.invoice_number == invoice_number)
        )
        invoice = result.scalar_one_or_none()
        if invoice is None or invoice.deleted_at is not None:
            raise ValueError(f"No invoice numbered {invoice_number}")

        return _dump(serialize_invoice(invoice, include_items=True, json_ready=True))


@mcp.resource(
    "client://{client_id}",
    name="Client",
    title="Client by ID",
    description="A single client's contact details, terms, and tax settings.",
    mime_type=_JSON,
)
async def client_resource(client_id: str) -> str:
    """Read one client by ID.

    The URI template hands parameters over as strings, so the ID is parsed
    here rather than declared as an int.
    """
    try:
        parsed = int(client_id)
    except ValueError:
        raise ValueError(f"Client id must be a number, got {client_id!r}") from None

    async with get_session() as session:
        client = await ClientService.get_client(session, parsed)
        if client is None:
            raise ValueError(f"No client with id {parsed}")

        return _dump(serialize_client(client, json_ready=True))


@mcp.resource(
    "invoices://outstanding",
    name="Outstanding invoices",
    title="Outstanding invoices",
    description=(
        "Every invoice still awaiting payment (sent, overdue, or partially "
        "paid), earliest due first. The working list for chasing money."
    ),
    mime_type=_JSON,
)
async def outstanding_invoices_resource() -> str:
    """List the invoices that are still owed."""
    async with get_session() as session:
        # Partial payment is not a status: a partly paid invoice is still sent or overdue.
        invoices = (
            await session.execute(
                select(Invoice)
                .where(
                    Invoice.status.in_(("sent", "overdue")),
                    Invoice.document_type == "invoice",
                    Invoice.deleted_at.is_(None),
                )
                .order_by(
                    Invoice.due_date.is_(None),
                    Invoice.due_date,
                    Invoice.created_at.desc(),
                    Invoice.id.desc(),
                )
                .limit(400)
            )
        ).scalars()

        return _dump(
            [
                serialize_invoice(
                    invoice,
                    include_items=False,
                    include_formatted_total=True,
                    json_ready=True,
                )
                for invoice in invoices
            ]
        )


@mcp.resource(
    "profile://business",
    name="Business profile",
    title="Business profile",
    description=(
        "The sending business's own details: name, address, currency, payment "
        "terms, and tax defaults. Useful context when drafting anything."
    ),
    mime_type=_JSON,
)
async def business_profile_resource() -> str:
    """Read the business profile. Secrets are never included."""
    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)
        return _dump(
            serialize_business_profile(profile, json_ready=True, payment_methods_as_list=True)
        )
