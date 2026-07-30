"""Output models describing what the MCP tools return.

Declaring these as tool return types gives every tool an `outputSchema`, so a
client knows the shape of a result before it calls and gets `structuredContent`
alongside the human-readable text instead of having to parse JSON out of a
string.

Two rules govern everything in this file, both about not corrupting data:

1. **Field types mirror exactly what `presenters.py` emits.** The SDK does not
   merely publish the schema - it runs `output_model.model_validate(result)`
   and re-dumps the validated model as the structured content. So a type that
   disagrees with reality does not fail loudly, it silently rewrites the
   payload. Money is the case that matters: the presenters emit amounts as
   strings (`"100.00"`) to preserve exact decimal values, and declaring those
   fields `float` would have Pydantic coerce them to `100.0` and reintroduce
   binary floating-point into invoice totals. Amounts are `str` here, always.

2. **Every model allows extras.** `serialize_invoice` grows optional keys
   depending on its flags (`items`, `line_items_preview`, `total_formatted`),
   and callers add their own. `extra="allow"` keeps unmodelled keys flowing
   through to the client rather than silently dropping them, and means adding a
   field to a presenter cannot break a tool.

All MCP tools serialize with `json_ready=True`, so dates arrive as ISO strings
and are typed `str` here rather than `date`/`datetime`.

One shape note for anyone reading results on the client side: a tool returning
a bare model (`-> ClientOut`) puts that model's fields at the top level of
`structuredContent`, but a tool returning `-> ClientOut | None` or
`-> list[ClientOut]` cannot, since neither is a JSON object. The SDK nests
those under a single `"result"` key.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Out(BaseModel):
    """Base for output models: permissive about extra keys, strict about types."""

    model_config = ConfigDict(extra="allow")


class ClientOut(_Out):
    """A client record as returned by the client tools."""

    id: int
    name: str | None = None
    business_name: str | None = None
    display_name: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    email: str | None = None
    phone: str | None = None
    payment_terms_days: int | None = None
    notes: str | None = None
    tax_enabled: int | None = None
    # json_ready renders the client's tax rate as a number, unlike invoice
    # amounts - it is a rate, not money, so float is faithful here.
    tax_rate: float | None = None
    tax_name: str | None = None
    preferred_currency: str | None = None
    is_active: bool | None = None
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None


class InvoiceItemOut(_Out):
    """A single line item. Quantity and amounts are strings, not numbers."""

    id: int
    description: str | None = None
    quantity: str | None = None
    unit_type: str | None = None
    unit_price: str | None = None
    total: str | None = None
    sort_order: int | None = None


class InvoiceOut(_Out):
    """An invoice or quote. Every monetary field is a decimal string."""

    id: int
    invoice_number: str | None = None
    document_type: str | None = None
    client_id: int | None = None
    client_name: str | None = None
    client_business: str | None = None
    client_address: str | None = None
    client_email: str | None = None
    client_reference: str | None = None
    status: str | None = None
    paid_at: str | None = None
    amount_paid: str | None = None
    amount_due: str | None = None
    is_partially_paid: bool | None = None
    issue_date: str | None = None
    due_date: str | None = None
    payment_terms_days: int | None = None
    currency_code: str | None = None
    subtotal: str | None = None
    tax_enabled: bool | None = None
    tax_rate: str | None = None
    tax_name: str | None = None
    tax_amount: str | None = None
    total: str | None = None
    notes: str | None = None
    show_payment_instructions: bool | None = None
    # Either a raw JSON string or a decoded list, depending on the caller's
    # flag, so this stays deliberately untyped.
    selected_payment_methods: object | None = None
    pdf_path: str | None = None
    pdf_generated_at: str | None = None
    exchange_rate: str | None = None
    base_currency_code: str | None = None
    converted_from_invoice_id: int | None = None
    converted_to_invoice_id: int | None = None
    payment_link_url: str | None = None
    payment_link_created_at: str | None = None
    last_reminder_sent_at: str | None = None
    reminders_sent: list | None = None
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    line_items_count: int | None = None
    items: list[InvoiceItemOut] | None = None


class PaymentOut(_Out):
    """A recorded payment, exactly as `serialize_payment` emits it."""

    id: int
    invoice_id: int | None = None
    amount: str | None = None
    currency_code: str | None = None
    payment_date: str | None = None
    method: str | None = None
    reference: str | None = None
    notes: str | None = None
    provider: str | None = None
    external_id: str | None = None
    created_at: str | None = None


class PaymentLedgerOut(_Out):
    """An invoice's payment history plus its current balance."""

    invoice_id: int
    invoice_number: str | None = None
    currency_code: str | None = None
    total: str | None = None
    amount_paid: str | None = None
    amount_due: str | None = None
    is_partially_paid: bool | None = None
    payments: list[PaymentOut] = []


class RecurringScheduleOut(_Out):
    """A recurring invoice schedule."""

    id: int
    client_id: int | None = None
    client_name: str | None = None
    client_business: str | None = None
    name: str | None = None
    frequency: str | None = None
    schedule_day: int | None = None
    schedule_month: int | None = None
    quarter_month: int | None = None
    currency_code: str | None = None
    payment_terms_days: int | None = None
    notes: str | None = None
    use_default_notes: bool | None = None
    line_items: list | None = None
    show_payment_instructions: bool | None = None
    selected_payment_methods: object | None = None
    auto_email_enabled: bool | None = None
    email_subject_template: str | None = None
    email_body_template: str | None = None
    tax_enabled: bool | None = None
    # json_ready renders the schedule's tax rate as a number, unlike invoice
    # amounts - it is a rate, not money, so float is faithful here.
    tax_rate: float | None = None
    tax_name: str | None = None
    is_active: bool | None = None
    next_invoice_date: str | None = None
    last_invoice_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
