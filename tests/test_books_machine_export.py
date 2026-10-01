"""Books Machine export: every record carried, and anything Books Machine refuses normalized with a warning."""

import json
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import (
    BusinessProfile,
    Client,
    Invoice,
    InvoiceItem,
    Payment,
    RecurringSchedule,
)
from invoice_machine.service.books_machine import build_books_machine_bundle


def _invoice(number: str, **fields) -> Invoice:
    defaults = {
        "issue_date": date(2026, 9, 1),
        "due_date": date(2026, 10, 1),
        "currency_code": "USD",
        "subtotal": Decimal("20.00"),
        "total": Decimal("20.00"),
        "status": "sent",
    }
    return Invoice(invoice_number=number, **{**defaults, **fields})


async def seed(session: AsyncSession) -> None:
    """Rows only legacy versions, MCP or direct edits could leave behind."""
    session.add(
        BusinessProfile(
            id=1,
            name="Ada",
            business_name="Analytical Engines",
            email="  ",
            fx_rates='{"eur": "0.9", "bad": "x", "GBP": "0"}',
            reminders_enabled=1,
            reminder_send_hour=7,
            logo_path="logo-missing.png",
            smtp_enabled=1,
        )
    )
    good = Client(id=1, name="Charles", business_name="Babbage & Co", email="charles@example.test")
    nameless = Client(id=2, email="a@x.test, b@x.test", notes="n" * 6000, preferred_currency="us")
    gone = Client(id=3, name="Gone", deleted_at=datetime(2026, 9, 2, 8, 30))
    marked = Client(id=4, name="\ufeff", tax_rate=Decimal("1e-100"))
    session.add_all([good, nameless, gone, marked])
    await session.flush()

    session.add_all(
        [
            _invoice(
                "INV/2026 001", id=1, client_id=1, client_business="Old Name Ltd", tax_enabled=1
            ),
            _invoice("LONG", id=2, client_id=1, total=Decimal("102.00")),
            _invoice(
                "CANCELLED-1", id=3, client_id=1, status="cancelled", amount_paid=Decimal("5.00")
            ),
            _invoice(
                "Q-1",
                id=4,
                client_id=1,
                document_type="quote",
                status="overdue",
                amount_paid=Decimal("3.00"),
            ),
            _invoice(
                "PAID-1",
                id=5,
                client_id=1,
                status="paid",
                amount_paid=Decimal("20.00"),
                paid_at=datetime(2026, 9, 3, 23, 30),
                reminders_sent="[7, 1, 999]",
            ),
            _invoice(
                "ORPHAN-LINK",
                id=6,
                client_id=3,
                converted_from_invoice_id=999,
                converted_to_invoice_id=5,
            ),
            _invoice("INV-1 ", id=7, client_id=2),
            _invoice("INV-1", id=8, client_id=None, exchange_rate=Decimal("5000000")),
            _invoice("EUR-1", id=9, client_id=1, currency_code="EUR", amount_paid=Decimal("1.00")),
            _invoice("A-12", id=10, client_id=1),
            _invoice("A", id=11, client_id=1),
            _invoice("/A", id=12, client_id=1),
            _invoice("BTC-1", id=13, client_id=1, currency_code="BTC"),
            _invoice("SETTLED", id=14, client_id=1, amount_paid=Decimal("20.00")),
            _invoice(
                "HUGE",
                id=15,
                client_id=1,
                selected_payment_methods=json.dumps(["\U0001f600" * 51, None]),
            ),
        ]
    )
    await session.flush()
    session.add(
        InvoiceItem(
            invoice_id=1, description="Work", quantity=Decimal("2"), unit_price=10, total=20
        )
    )
    session.add(
        InvoiceItem(
            invoice_id=13, description="Huge", quantity=1, unit_price=Decimal("1e13"), total=0
        )
    )
    session.add_all(
        InvoiceItem(invoice_id=15, description="Big", unit_price=Decimal("999999999999"), total=0)
        for _ in range(10)
    )
    session.add_all(
        InvoiceItem(
            invoice_id=2, description=f"Line {n}", quantity=1, unit_price=1, total=1, sort_order=n
        )
        for n in range(102)
    )
    session.add(
        InvoiceItem(
            invoice_id=7,
            description="Bulk",
            quantity=Decimal("20000"),
            unit_price=Decimal("0.01"),
            total=200,
        )
    )
    session.add_all(
        [
            Payment(invoice_id=3, amount=Decimal("5.00"), payment_date=date(2026, 9, 2)),
            Payment(invoice_id=4, amount=Decimal("3.00"), payment_date=date(2026, 9, 2)),
            Payment(invoice_id=14, amount=Decimal("20.00"), payment_date=date(2026, 9, 2)),
            Payment(
                invoice_id=9,
                amount=Decimal("1.00"),
                currency_code="GBP",
                payment_date=date(2026, 9, 2),
            ),
            Payment(
                invoice_id=5,
                amount=Decimal("20.00"),
                payment_date=date(2026, 9, 3),
                method="system_mark_paid",
                notes="Marked paid",
            ),
        ]
    )
    session.add(
        RecurringSchedule(
            id=1,
            client_id=1,
            name="  ",
            frequency="monthly",
            next_invoice_date=date(2026, 11, 1),
            line_items=json.dumps(
                [{"description": "Retainer", "quantity": 1, "unit_price": "100"}, "junk"]
            ),
            last_invoice_id=8,
        )
    )
    await session.commit()
    # SQLite keeps the scale the ORM would round away on read.
    await session.execute(text("UPDATE invoices SET tax_rate = 8.875 WHERE id = 1"))
    await session.commit()


@pytest.mark.asyncio
async def test_bundle_normalizes_what_books_machine_refuses(db_session: AsyncSession):
    await seed(db_session)
    bundle = await build_books_machine_bundle(db_session)
    warnings = "\n".join(bundle["warnings"])
    invoices = {invoice["sourceId"]: invoice for invoice in bundle["invoices"]}

    assert bundle["manifest"]["format"] == "invoice-machine-import"
    assert bundle["manifest"]["createdAt"].endswith("Z")
    assert len(bundle["clients"]) == 4 and len(invoices) == 15

    profile = bundle["profile"]
    assert profile["businessEmail"] is None
    assert json.loads(profile["fxRates"]) == {"EUR": "0.9"}
    assert profile["reminderOffsets"] == "[-3,1,7,14]"
    assert (profile["remindersEnabled"], profile["reminderSendHour"]) == (True, 7)
    assert bundle["logo"] is None and "logo-missing.png" in warnings
    assert "SMTP" in warnings

    nameless = bundle["clients"][1]["data"]
    assert nameless["email"] is None and "is not a single valid address" in warnings
    assert nameless["name"] == "Client 2"
    assert len(nameless["notes"]) == 5000
    assert nameless["preferredCurrency"] is None
    assert bundle["clients"][2]["deletedAt"] == "2026-09-02T08:30:00.000Z"

    first = invoices["1"]
    assert first["data"]["invoiceNumberOverride"] == "INV-2026-001"
    assert first["data"]["taxRate"] == "8.875"
    assert first["clientSnapshot"]["business"] == "Old Name Ltd"
    assert first["expectedTotal"] == "20.00"

    long_items = invoices["2"]["data"]["items"]
    assert len(long_items) == 100
    assert long_items[-1] == {
        "description": "Combined 3 further lines",
        "quantity": "1",
        "unitType": "qty",
        "unitPrice": "3.00",
        "sortOrder": 99,
    }

    assert (
        invoices["3"]["status"] == "sent" and "cannot cancel an invoice with payments" in warnings
    )
    assert invoices["4"]["status"] == "sent" and invoices["4"]["payments"] == []

    paid = invoices["5"]
    assert paid["paidAt"] == "2026-09-03"
    assert paid["remindersSent"] == [1, 7]
    assert paid["payments"][0]["data"]["method"] == "system_mark_paid"

    orphan = invoices["6"]
    assert orphan["convertedFromSourceId"] is None
    assert orphan["convertedToSourceId"] is None

    trailing, plain = invoices["7"]["data"], invoices["8"]["data"]
    assert trailing["invoiceNumberOverride"] == "INV-1-7"
    assert plain["invoiceNumberOverride"] == "INV-1"
    assert "duplicates another invoice" in warnings
    assert trailing["items"][0]["quantity"] == "1" and trailing["items"][0]["unitPrice"] == "200"
    assert plain["exchangeRate"] is None

    assert [invoices[i]["data"]["invoiceNumberOverride"] for i in ("10", "11", "12")] == [
        "A-12",
        "A",
        "A-12-2",
    ]
    btc = invoices["13"]["data"]
    assert btc["currencyCode"] == "USD" and btc["items"] == []
    assert "unrecognized currency 'BTC'" in warnings and "'Huge' with an unusable price" in warnings
    marked = bundle["clients"][3]["data"]
    assert marked["name"] == "Client 4" and marked["taxRate"] == "0"
    huge = invoices["15"]["data"]
    assert huge["items"] == [] and "too large to import" in warnings
    assert huge["selectedPaymentMethods"] == ["\U0001f600" * 50]
    assert "Invoice SETTLED is marked sent but its payments cover the total" in warnings
    assert "Invoice EUR-1 has payments recorded in another currency" in warnings
    assert "Invoice EUR-1 in EUR has no recorded exchange rate" in warnings

    [schedule] = bundle["recurringSchedules"]
    assert schedule["data"]["name"] == "Recurring schedule 1"
    assert schedule["lastInvoiceSourceId"] == "8"
    assert [item["description"] for item in schedule["data"]["items"]] == ["Retainer"]
