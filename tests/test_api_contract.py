"""Keep the frontend's API typedefs honest about what the API actually returns.

`frontend/src/lib/types.js` describes the shapes the SPA consumes. Nothing makes
the browser check those against reality, so a field added to a serializer and
not to the typedef (or removed from one side only) would go unnoticed until
something rendered `undefined`.

This parses the typedefs and compares them field-by-field with what the
serializers in `invoice_machine/presenters.py` emit.
"""

import datetime
import re
from decimal import Decimal
from pathlib import Path

import pytest

from invoice_machine import presenters
from invoice_machine.database import (
    Client,
    Invoice,
    InvoiceItem,
    Payment,
    RecurringSchedule,
)

TYPES_FILE = Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib" / "types.js"


def _typedef_fields(source: str, name: str) -> set[str]:
    """Extract the @property names from one @typedef block."""
    match = re.search(rf"@typedef \{{Object\}} {name}\b(.*?)(?=\n \*/)", source, re.S)
    if not match:
        raise AssertionError(f"types.js has no @typedef for {name}")
    # @property {type} name  /  @property {type} [name] for optional
    return {
        field.strip("[]")
        for field in re.findall(r"@property \{[^}]*\}\s+(\[?[A-Za-z_][\w]*\]?)", match.group(1))
    }


def _now() -> datetime.datetime:
    return datetime.datetime(2026, 1, 1, 12, 0)


def _sample_invoice() -> Invoice:
    invoice = Invoice(
        id=1,
        invoice_number="20260101-1",
        issue_date=datetime.date(2026, 1, 1),
        subtotal=Decimal("0.00"),
        total=Decimal("0.00"),
        amount_paid=Decimal("0.00"),
        created_at=_now(),
        updated_at=_now(),
    )
    invoice.items = []
    return invoice


def _sample_schedule() -> RecurringSchedule:
    schedule = RecurringSchedule(
        id=1,
        client_id=1,
        name="Retainer",
        frequency="monthly",
        schedule_day=1,
        quarter_month=1,
        currency_code="USD",
        payment_terms_days=30,
        is_active=1,
        use_default_notes=1,
        show_payment_instructions=1,
        auto_email_enabled=0,
        next_invoice_date=datetime.date(2026, 2, 1),
        created_at=_now(),
        updated_at=_now(),
    )
    schedule.client = None
    return schedule


def _profile_schema_fields() -> set[str]:
    """`GET /api/profile` declares a response_model, so the Pydantic schema, not
    the presenter, decides what the SPA receives."""
    from invoice_machine.api.profile import BusinessProfileSchema

    return dict.fromkeys(BusinessProfileSchema.model_fields)


SERIALIZED = {
    "BusinessProfile": _profile_schema_fields,
    "Invoice": lambda: presenters.serialize_invoice(_sample_invoice(), json_ready=True),
    "InvoiceItem": lambda: presenters.serialize_invoice_item(
        InvoiceItem(
            id=1,
            description="Service",
            quantity=Decimal("1"),
            unit_type="qty",
            unit_price=Decimal("1.00"),
            total=Decimal("1.00"),
            sort_order=0,
        )
    ),
    "Client": lambda: presenters.serialize_client(
        Client(id=1, created_at=_now(), updated_at=_now()), json_ready=True
    ),
    "Payment": lambda: presenters.serialize_payment(
        Payment(
            id=1,
            invoice_id=1,
            amount=Decimal("1.00"),
            currency_code="USD",
            payment_date=datetime.date(2026, 1, 1),
            created_at=_now(),
        ),
        json_ready=True,
    ),
    "RecurringSchedule": lambda: presenters.serialize_recurring_schedule(
        _sample_schedule(), json_ready=True
    ),
}


@pytest.mark.parametrize("entity", sorted(SERIALIZED))
def test_frontend_typedef_matches_serializer(entity):
    source = TYPES_FILE.read_text(encoding="utf-8")
    declared = _typedef_fields(source, entity)
    actual = set(SERIALIZED[entity]().keys())

    missing = actual - declared
    extra = declared - actual

    assert not missing, (
        f"{entity} gained {sorted(missing)} in presenters.py; add them to "
        f"frontend/src/lib/types.js so the SPA knows about them"
    )
    assert not extra, (
        f"{entity} declares {sorted(extra)} in types.js that the API no longer returns; remove them"
    )


def test_types_file_is_reachable():
    """A moved or renamed types.js should fail loudly rather than skip silently."""
    assert TYPES_FILE.exists(), f"expected the frontend typedefs at {TYPES_FILE}"
