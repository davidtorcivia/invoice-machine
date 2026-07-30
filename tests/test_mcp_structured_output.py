"""Tests for the MCP tools' structured output.

The SDK does not just publish `outputSchema` - it validates each result against
the declared model and re-dumps it as `structuredContent`. That makes a wrong
annotation a data corruption bug rather than a loud failure: declare a money
field as a float and `"100.00"` silently becomes `100.0`.

So these tests assert the round trip, not just the presence of a schema.
"""

import pytest
import pytest_asyncio
from mcp.client import Client

from invoice_machine.mcp import client_tools, invoice_tools


@pytest_asyncio.fixture(scope="function")
async def mcp_db():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    import invoice_machine.database as db
    from invoice_machine.database import Base, register_sqlite_pragmas
    from invoice_machine.mcp import context

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    register_sqlite_pragmas(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    original_maker = db.async_session_maker
    db.async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    original_initialized = context._schema_initialized
    context._schema_initialized = True

    yield

    db.async_session_maker = original_maker
    context._schema_initialized = original_initialized
    await engine.dispose()


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
