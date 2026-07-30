"""MCP resources: addressable views of invoices, clients, and the business.

Tools are verbs; resources are nouns. A client that wants to *look at* invoice
20250115-1 should not have to call a tool and hope the model passes the right
integer ID - it can read `invoice://20250115-1` directly, attach it to a
conversation, or let a user browse to it.

Resources also cost less than tool calls. Under spec 2026-07-28 `resources/read`
carries `ttlMs`/`cacheScope`, so a client can cache what it has already read
instead of re-fetching on every turn.

URIs use the human-facing identifier where one exists: invoices are addressed by
their number (`20250115-1`), which is what appears on the document and what a
person will type, not their database ID. Clients have no such identifier, so
they are addressed by ID.

Everything here is read-only by construction - these functions only ever select.
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
from invoice_machine.services import ClientService, InvoiceService

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
        "paid), newest first. The working list for chasing money."
    ),
    mime_type=_JSON,
)
async def outstanding_invoices_resource() -> str:
    """List the invoices that are still owed.

    Deliberately a fixed URI rather than a template: "what am I owed" is a
    question with one answer, and making it addressable means a client can
    attach it without first deciding which filters to pass a tool.
    """
    async with get_session() as session:
        invoices = []
        for status in ("sent", "overdue", "partially_paid"):
            invoices.extend(
                await InvoiceService.list_invoices(
                    session, status=status, document_type="invoice", limit=200
                )
            )

        invoices.sort(key=lambda inv: (inv.due_date is None, inv.due_date))

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
        # serialize_business_profile reports only whether keys and passwords
        # are configured, never their values.
        return _dump(
            serialize_business_profile(
                profile, json_ready=True, payment_methods_as_list=True
            )
        )
