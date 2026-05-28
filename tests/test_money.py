"""Tests for money quantization and multi-currency handling."""

from decimal import Decimal

import pytest

from invoice_machine.service.common import format_quantity, line_item_total, quantize_money
from invoice_machine.services import InvoiceService


def test_format_quantity_strips_trailing_zeros():
    assert format_quantity(Decimal("1.500")) == "1.5"
    assert format_quantity(Decimal("2")) == "2"
    assert format_quantity("0.250") == "0.25"
    assert format_quantity(3) == "3"


def test_quantize_money_rounds_half_up():
    assert quantize_money("10.005") == Decimal("10.01")
    assert quantize_money(Decimal("32.997")) == Decimal("33.00")
    # classic binary-float trap
    assert quantize_money(0.1 + 0.2) == Decimal("0.30")


def test_line_item_total_is_quantized():
    assert line_item_total("10.999", 3) == Decimal("33.00")
    assert line_item_total(Decimal("0.1"), 3) == Decimal("0.30")
    # string quantity (as an MCP/LLM client might send) must not crash
    assert line_item_total("100", "2") == Decimal("200.00")


@pytest.mark.asyncio
async def test_invoice_totals_reconcile_to_cents(db_session, test_client):
    """subtotal + tax == total, all at 2 decimal places, no sub-cent drift."""
    invoice = await InvoiceService.create_invoice(
        db_session,
        client_id=test_client.id,
        items=[
            {"description": "A", "quantity": 3, "unit_price": "10.999"},
            {"description": "B", "quantity": 1, "unit_price": "0.1"},
        ],
        tax_enabled=True,
        tax_rate=Decimal("8.25"),
    )

    cents = Decimal("0.01")
    assert invoice.subtotal == Decimal("33.10")  # 33.00 + 0.10
    assert invoice.tax_amount == quantize_money(invoice.subtotal * Decimal("8.25") / Decimal("100"))
    assert invoice.total == invoice.subtotal + invoice.tax_amount
    for value in (invoice.subtotal, invoice.tax_amount, invoice.total):
        assert value == value.quantize(cents)


@pytest.mark.asyncio
async def test_fractional_hours_quantity(db_session, test_client):
    """1.5 hours at $100 must bill $150 (quantity is no longer truncated)."""
    invoice = await InvoiceService.create_invoice(
        db_session,
        client_id=test_client.id,
        items=[
            {"description": "Consulting", "quantity": "1.5", "unit_type": "hours", "unit_price": "100"}
        ],
    )
    assert invoice.items[0].quantity == Decimal("1.500")
    assert invoice.items[0].total == Decimal("150.00")
    assert invoice.subtotal == Decimal("150.00")


@pytest.mark.asyncio
async def test_client_stats_do_not_mix_currencies(db_session, test_client):
    """A client's USD and EUR invoices are reported per-currency, never summed."""
    from invoice_machine.services import ClientService

    await InvoiceService.create_invoice(
        db_session,
        client_id=test_client.id,
        currency_code="USD",
        items=[{"description": "usd", "quantity": 1, "unit_price": "1000"}],
    )
    await InvoiceService.create_invoice(
        db_session,
        client_id=test_client.id,
        currency_code="EUR",
        items=[{"description": "eur", "quantity": 1, "unit_price": "500"}],
    )

    stats = await ClientService.get_client_invoice_stats(db_session, client_id=test_client.id)
    assert len(stats) == 1
    stat = stats[0]
    # Both currencies are tracked separately
    assert set(stat["by_currency"].keys()) == {"USD", "EUR"}
    assert stat["by_currency"]["USD"]["invoiced"] == "1000.00"
    assert stat["by_currency"]["EUR"]["invoiced"] == "500.00"
    # Headline total reflects a single (dominant) currency, never 1500
    assert stat["total_invoiced"] in (Decimal("1000.00"), Decimal("500.00"))
    assert stat["invoice_count"] == 2
