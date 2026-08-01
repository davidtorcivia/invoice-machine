"""Tests for the MCP tools' structured output.

The SDK does not just publish `outputSchema` - it validates each result against
the declared model and re-dumps it as `structuredContent`. That makes a wrong
annotation a data corruption bug rather than a loud failure: declare a money
field as a float and `"100.00"` silently becomes `100.0`.

So these tests assert the round trip, not just the presence of a schema.
"""

import pytest
from mcp.client import Client

from invoice_machine.mcp import client_tools, invoice_tools


def _server():
    from invoice_machine.mcp.server import mcp

    return mcp


def _unwrap(structured):
    """Return the payload, accounting for how the SDK wraps non-object results.

    A tool returning a bare model puts its fields at the top level. A tool
    returning `Model | None` or `list[Model]` cannot - neither is a JSON object
    - so the SDK nests it under a single "result" key.
    """
    if isinstance(structured, dict) and set(structured) == {"result"}:
        return structured["result"]
    return structured


@pytest.mark.asyncio
async def test_tools_publish_output_schemas(mcp_db):
    """The entity tools describe their results instead of returning loose JSON."""
    async with Client(_server()) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    for name in [
        "list_clients",
        "get_client",
        "create_client",
        "list_invoices",
        "get_invoice",
        "create_invoice",
        "list_payments",
        "list_recurring_schedules",
        "create_recurring_schedule",
    ]:
        assert tools[name].output_schema, f"{name} has no outputSchema"


@pytest.mark.asyncio
async def test_money_survives_the_round_trip_as_exact_strings(mcp_db):
    """Amounts must reach the client byte-identical, never as floats.

    0.1 + 0.2 is the classic float trap; an invoice for 1234.56 must not come
    back as 1234.5599999999999.
    """
    client_rec = await client_tools.create_client(name="Precision Co")
    created = await invoice_tools.create_invoice(
        client_id=client_rec["id"],
        items=[{"description": "Consulting", "quantity": 1, "unit_price": "1234.56"}],
    )

    async with Client(_server()) as mcp_client:
        result = await mcp_client.call_tool("get_invoice", {"invoice_id": created["id"]})

    assert result.structured_content is not None, "expected structuredContent"
    structured = _unwrap(result.structured_content)

    assert structured["total"] == "1234.56"
    assert isinstance(structured["total"], str)
    assert isinstance(structured["subtotal"], str)
    # Every amount field stays a string - no silent float coercion anywhere.
    for field in ("amount_paid", "amount_due", "tax_amount"):
        assert isinstance(structured[field], str), (
            f"{field} was coerced to {type(structured[field])}"
        )


@pytest.mark.asyncio
async def test_structured_content_matches_the_tool_return(mcp_db):
    """Validation must not drop or rewrite fields the tool actually returned."""
    created = await client_tools.create_client(
        name="Roundtrip", email="rt@example.test", payment_terms_days=45
    )

    async with Client(_server()) as mcp_client:
        result = await mcp_client.call_tool("get_client", {"client_id": created["id"]})

    structured = _unwrap(result.structured_content)
    for key, value in created.items():
        assert structured[key] == value, f"{key} changed: {value!r} -> {structured[key]!r}"


@pytest.mark.asyncio
async def test_unmodelled_keys_are_not_dropped(mcp_db):
    """extra="allow" keeps presenter-added keys that the model does not name.

    list_invoices asks for a formatted total and a line-item preview; neither is
    a field on InvoiceOut, and both must still reach the client.
    """
    client_rec = await client_tools.create_client(name="Extras")
    await invoice_tools.create_invoice(
        client_id=client_rec["id"],
        items=[{"description": "Design work", "quantity": 2, "unit_price": "50.00"}],
    )

    async with Client(_server()) as mcp_client:
        result = await mcp_client.call_tool("list_invoices", {})

    rows = _unwrap(result.structured_content)
    assert rows, "expected at least one invoice"
    assert "total_formatted" in rows[0], "presenter-added key was dropped"
    assert "line_items_preview" in rows[0]


@pytest.mark.asyncio
async def test_nullable_result_still_validates(mcp_db):
    """A miss returns null rather than failing schema validation."""
    async with Client(_server()) as mcp_client:
        result = await mcp_client.call_tool("get_client", {"client_id": 999999})

    assert not result.is_error


@pytest.mark.asyncio
async def test_record_payment_requires_an_idempotency_key(mcp_db):
    """The tool schema forces a key, so a retry cannot silently double-record."""
    async with Client(_server()) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    schema = tools["record_payment"].input_schema
    assert "idempotency_key" in schema["required"]
    # And it is now advertised as safe to retry.
    assert tools["record_payment"].annotations.idempotent_hint is True


@pytest.mark.asyncio
async def test_record_payment_replay_does_not_double_count(mcp_db):
    """Calling the tool twice with one key leaves a single payment."""
    client_rec = await client_tools.create_client(name="Retry Co")
    created = await invoice_tools.create_invoice(
        client_id=client_rec["id"],
        items=[{"description": "Work", "quantity": 1, "unit_price": "100.00"}],
    )
    await invoice_tools.update_invoice(invoice_id=created["id"], status="sent")

    args = {
        "invoice_id": created["id"],
        "amount": 40.0,
        "idempotency_key": "mcp-retry-1",
    }
    async with Client(_server()) as client:
        first = await client.call_tool("record_payment", args)
        second = await client.call_tool("record_payment", args)
        ledger = await client.call_tool("list_payments", {"invoice_id": created["id"]})

    assert not first.is_error and not second.is_error

    # record_payment returns a success/error envelope rather than a bare entity,
    # so it publishes no output model; the ledger is where the effect shows.
    ledger_data = _unwrap(ledger.structured_content)
    payments = ledger_data["payments"]
    assert len(payments) == 1, f"expected one payment, got {len(payments)}"
    assert ledger_data["amount_paid"] == "40.00", "the retry was counted twice"


@pytest.mark.asyncio
async def test_every_tool_is_annotated(mcp_db):
    """No tool may ship unlabelled.

    Annotations are how a client tells a lookup from something that moves money.
    A tool added without them silently reads as "unknown risk", so this guards
    the whole set rather than any single tool.
    """
    async with Client(_server()) as client:
        tools = (await client.list_tools()).tools

    missing = sorted(t.name for t in tools if t.annotations is None)
    assert not missing, f"tools without annotations: {missing}"
