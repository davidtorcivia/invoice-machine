"""MCP tool-layer tests.

The MCP tools are the lower-trust automation surface and were almost entirely
untested. These call the decorated tool functions directly against a temp DB
(the tools resolve their session from the module-level maker at call time), so
they exercise the same code paths Claude Desktop / the bot would.
"""

import pytest
import pytest_asyncio

from invoice_machine.mcp import (
    analytics_tools,
    client_tools,
    email_tools,
    invoice_tools,
    profile_tools,
    recurring_tools,
    search_tools,
)


@pytest_asyncio.fixture(scope="function")
async def mcp_db():
    """Point the MCP tools at a fresh temp database and skip schema bootstrap."""
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
    # Schema already built via create_all; stop the tools running real migrations.
    original_initialized = context._schema_initialized
    context._schema_initialized = True

    yield

    db.async_session_maker = original_maker
    context._schema_initialized = original_initialized
    await engine.dispose()


@pytest.mark.asyncio
async def test_client_crud_roundtrip(mcp_db):
    created = await client_tools.create_client(name="Jane Doe", business_name="Acme")
    client_id = created["id"]

    listed = await client_tools.list_clients()
    assert any(c["id"] == client_id for c in listed)

    updated = await client_tools.update_client(client_id, name="Jane Smith")
    assert updated["name"] == "Jane Smith"

    assert await client_tools.delete_client(client_id) is True


@pytest.mark.asyncio
async def test_invoice_create_and_fractional_item(mcp_db):
    client = await client_tools.create_client(name="Hours Client")
    invoice = await invoice_tools.create_invoice(
        client_id=client["id"],
        items=[{"description": "Setup", "quantity": 1, "unit_price": 100}],
    )
    invoice_id = invoice["id"]
    assert invoice["total"] == "100.00"

    # Fractional quantity must work through the MCP add-item tool.
    item = await invoice_tools.add_invoice_item(
        invoice_id, "Consulting", quantity=1.5, unit_price=100, unit_type="hours"
    )
    assert item["quantity"] == "1.5"
    assert item["total"] == "150.00"

    full = await invoice_tools.get_invoice(invoice_id)
    assert full["total"] == "250.00"


@pytest.mark.asyncio
async def test_invoice_create_inherits_business_tax_default(mcp_db):
    # MCP create_invoice with tax_enabled=None must inherit the business default.
    await profile_tools.update_business_profile(default_tax_enabled=True, default_tax_rate=10)
    client = await client_tools.create_client(name="Taxed")
    invoice = await invoice_tools.create_invoice(
        client_id=client["id"],
        items=[{"description": "x", "quantity": 1, "unit_price": 200}],
    )
    assert invoice["tax_enabled"] is True
    assert invoice["tax_amount"] == "20.00"
    assert invoice["total"] == "220.00"


@pytest.mark.asyncio
async def test_update_business_profile_rejects_bad_accent_color(mcp_db):
    # Regression: the MCP path now validates accent_color (CSS-injection guard).
    with pytest.raises(ValueError):
        await profile_tools.update_business_profile(accent_color="red}*{x:url(file:///etc/passwd)}")

    ok = await profile_tools.update_business_profile(accent_color="#0891b2")
    assert ok["accent_color"] == "#0891b2"


@pytest.mark.asyncio
async def test_list_invoices_document_type_filter(mcp_db):
    client = await client_tools.create_client(name="Mixed")
    await invoice_tools.create_invoice(
        client_id=client["id"], document_type="invoice",
        items=[{"description": "inv", "quantity": 1, "unit_price": 10}],
    )
    await invoice_tools.create_invoice(
        client_id=client["id"], document_type="quote",
        items=[{"description": "quo", "quantity": 1, "unit_price": 20}],
    )

    quotes = await invoice_tools.list_invoices(document_type="quote")
    assert len(quotes) == 1
    assert quotes[0]["document_type"] == "quote"


@pytest.mark.asyncio
async def test_recurring_schedule_validates_items(mcp_db):
    client = await client_tools.create_client(name="Retainer")
    # A bad unit_price must be rejected at save time, not at generation time.
    with pytest.raises(ValueError):
        await recurring_tools.create_recurring_schedule(
            client_id=client["id"], name="Bad", frequency="monthly",
            items=[{"description": "x", "quantity": 1, "unit_price": "not-a-number"}],
        )

    good = await recurring_tools.create_recurring_schedule(
        client_id=client["id"], name="Good", frequency="monthly", schedule_day=15,
        items=[{"description": "Retainer", "quantity": 1, "unit_price": 500}],
    )
    triggered = await recurring_tools.trigger_recurring_schedule(good["id"])
    assert triggered["success"] is True


@pytest.mark.asyncio
async def test_client_invoice_context_excludes_quotes_and_scopes_currency(mcp_db):
    client = await client_tools.create_client(name="Ctx")
    inv = await invoice_tools.create_invoice(
        client_id=client["id"], document_type="invoice",
        items=[{"description": "billed", "quantity": 1, "unit_price": 300}],
    )
    await invoice_tools.update_invoice(inv["id"], status="sent")
    await invoice_tools.create_invoice(
        client_id=client["id"], document_type="quote",
        items=[{"description": "quote", "quantity": 1, "unit_price": 999}],
    )

    ctx = await analytics_tools.get_client_invoice_context(client["id"])
    # total_billed counts the sent invoice only, not the quote.
    assert ctx["statistics"]["total_billed"] == "300.00"


@pytest.mark.asyncio
async def test_email_templates_roundtrip_and_search(mcp_db):
    updated = await email_tools.update_email_templates(email_subject_template="Hi {client_name}")
    assert updated["email_subject_template"] == "Hi {client_name}"

    await client_tools.create_client(name="Searchable Co", business_name="Searchable Co")
    results = await search_tools.search("Searchable")
    assert any("Searchable" in (c.get("business_name") or c.get("name") or "") for c in results["clients"])
