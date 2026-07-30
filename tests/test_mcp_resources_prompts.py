"""Tests for MCP resources and prompts.

Resources are the read-only, addressable half of the server: a client should be
able to fetch invoice://20250115-1 without going through a tool. These drive a
real client so URI templating, parameter parsing, and error handling all run.
"""

import json

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


def _text(result):
    """Pull the text payload out of a resources/read result."""
    return result.contents[0].text


@pytest.mark.asyncio
async def test_invoice_is_addressable_by_its_number(mcp_db):
    """The URI uses the number on the document, not the database ID."""
    client_rec = await client_tools.create_client(name="Resource Co")
    created = await invoice_tools.create_invoice(
        client_id=client_rec["id"],
        items=[{"description": "Work", "quantity": 1, "unit_price": "250.00"}],
    )
    number = created["invoice_number"]

    async with Client(_server()) as client:
        result = await client.read_resource(f"invoice://{number}")

    payload = json.loads(_text(result))
    assert payload["invoice_number"] == number
    assert payload["total"] == "250.00"
    # Reading an invoice should include what is on it.
    assert payload["items"], "expected line items in the invoice resource"


@pytest.mark.asyncio
async def test_client_resource_parses_its_id(mcp_db):
    """URI template parameters arrive as strings and must be coerced."""
    created = await client_tools.create_client(name="Addressable", email="a@b.test")

    async with Client(_server()) as client:
        result = await client.read_resource(f"client://{created['id']}")

    payload = json.loads(_text(result))
    assert payload["id"] == created["id"]
    assert payload["email"] == "a@b.test"


@pytest.mark.asyncio
async def test_outstanding_excludes_drafts_and_paid(mcp_db):
    """The chase list must only contain money actually owed."""
    client_rec = await client_tools.create_client(name="Owes Money")
    draft = await invoice_tools.create_invoice(
        client_id=client_rec["id"],
        items=[{"description": "Draft work", "quantity": 1, "unit_price": "10.00"}],
    )
    sent = await invoice_tools.create_invoice(
        client_id=client_rec["id"],
        items=[{"description": "Sent work", "quantity": 1, "unit_price": "20.00"}],
    )
    await invoice_tools.update_invoice(invoice_id=sent["id"], status="sent")

    async with Client(_server()) as client:
        result = await client.read_resource("invoices://outstanding")

    numbers = {row["invoice_number"] for row in json.loads(_text(result))}
    assert sent["invoice_number"] in numbers
    assert draft["invoice_number"] not in numbers, "a draft is not outstanding"


@pytest.mark.asyncio
async def test_business_profile_resource_leaks_no_secrets(mcp_db):
    """The profile resource reports that keys exist, never what they are."""
    async with Client(_server()) as client:
        result = await client.read_resource("profile://business")

    payload = json.loads(_text(result))
    assert "mcp_api_key_configured" in payload
    for secret in ("mcp_api_key", "bot_api_key", "smtp_password", "stripe_secret_key"):
        assert secret not in payload, f"{secret} must not be exposed"


@pytest.mark.asyncio
async def test_unknown_invoice_number_is_an_error(mcp_db):
    """A missing resource fails rather than returning an empty document."""
    async with Client(_server()) as client:
        with pytest.raises(Exception):
            await client.read_resource("invoice://does-not-exist")


@pytest.mark.asyncio
async def test_prompts_are_offered_with_their_arguments(mcp_db):
    async with Client(_server()) as client:
        listed = await client.list_prompts()

    by_name = {p.name: p for p in listed.prompts}
    assert set(by_name) == {"draft_invoice", "chase_overdue", "month_end_summary"}
    assert {a.name for a in by_name["draft_invoice"].arguments} == {"client", "work"}


@pytest.mark.asyncio
async def test_draft_invoice_prompt_withholds_sending(mcp_db):
    """The drafting prompt must not authorise the one irreversible step."""
    async with Client(_server()) as client:
        result = await client.get_prompt("draft_invoice", {"client": "Acme"})

    text = " ".join(m.content.text for m in result.messages if getattr(m.content, "text", None))
    assert "Acme" in text
    assert "do not email" in text.lower()


@pytest.mark.asyncio
async def test_chase_overdue_prompt_points_at_the_resource(mcp_db):
    """The prompt should send the model to the cheap resource, not a tool sweep."""
    async with Client(_server()) as client:
        result = await client.get_prompt("chase_overdue", {})

    text = " ".join(m.content.text for m in result.messages if getattr(m.content, "text", None))
    assert "invoices://outstanding" in text
    assert "do not send" in text.lower()
