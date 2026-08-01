"""Tests for the confirmation prompts on irreversible MCP tools.

These drive a real in-memory MCP client against the server so the whole
resolver path runs: the framework asks, the client answers, and the answer is
injected into the tool. Calling the tool functions directly (as
test_mcp_tools.py does) would skip exactly the machinery under test.

The three cases that matter:
  - the client answers yes  -> the tool runs
  - the client answers no   -> the tool does not run
  - the client cannot be asked at all -> the tool still runs, because failing
    closed here would break every client without elicitation support
"""

import pytest
import pytest_asyncio
from mcp.client import Client

from invoice_machine.mcp import client_tools, invoice_tools


@pytest_asyncio.fixture
async def invoice(mcp_db):
    """An invoice with a client email, ready to be sent."""
    client = await client_tools.create_client(name="Acme", email="ap@acme.test")
    return await invoice_tools.create_invoice(
        client_id=client["id"],
        items=[{"description": "Work", "quantity": 1, "unit_price": 100}],
    )


def _server():
    from invoice_machine.mcp.server import mcp

    return mcp


def _asked_and_answer(answer: bool):
    """An elicitation callback that records the prompt and answers `answer`."""
    seen: list[str] = []

    async def callback(context, params):
        from mcp_types import ElicitResult

        seen.append(params.message)
        return ElicitResult(action="accept", content={"confirm": answer})

    return seen, callback


@pytest.mark.asyncio
async def test_send_email_asks_before_sending(invoice):
    """The user is asked, and the prompt names the actual recipient."""
    seen, callback = _asked_and_answer(True)

    async with Client(_server(), elicitation_callback=callback) as client:
        result = await client.call_tool("send_invoice_email", {"invoice_id": invoice["id"]})

    assert len(seen) == 1, "expected exactly one confirmation prompt"
    # The risk being confirmed is "this reaches that person", so the address
    # has to appear in the question.
    assert "ap@acme.test" in seen[0]
    assert invoice["invoice_number"] in seen[0]
    # SMTP is not configured in this fixture, so the send itself fails - but it
    # got past the confirmation, which is what this test is about.
    assert result is not None


@pytest.mark.asyncio
async def test_declining_stops_the_send(invoice, monkeypatch):
    """Answering no must stop the email, not just record a preference."""
    sent = []

    async def fake_send(*args, **kwargs):
        sent.append(kwargs)
        return {"success": True}

    monkeypatch.setattr("invoice_machine.service.email.send_invoice_email", fake_send)

    async def decline(context, params):
        from mcp_types import ElicitResult

        return ElicitResult(action="decline")

    async with Client(_server(), elicitation_callback=decline) as client:
        result = await client.call_tool("send_invoice_email", {"invoice_id": invoice["id"]})

    assert sent == [], "declining must not send the email"
    assert result.is_error, "a declined call should surface as an error"


@pytest.mark.asyncio
async def test_accepting_but_answering_no_stops_the_send(invoice, monkeypatch):
    """A client can accept the form and still answer no; that means stop."""
    sent = []

    async def fake_send(*args, **kwargs):
        sent.append(kwargs)
        return {"success": True}

    monkeypatch.setattr("invoice_machine.service.email.send_invoice_email", fake_send)

    _, callback = _asked_and_answer(False)

    async with Client(_server(), elicitation_callback=callback) as client:
        result = await client.call_tool("send_invoice_email", {"invoice_id": invoice["id"]})

    assert sent == [], "an explicit no must not send the email"
    assert result.is_error


@pytest.mark.asyncio
async def test_client_without_elicitation_is_not_blocked(invoice, monkeypatch):
    """A client that cannot be asked still gets to send.

    This is the regression guard for the graceful-degradation branch: if the
    resolver returned an Elicit marker unconditionally, the SDK would fail the
    call with MISSING_REQUIRED_CLIENT_CAPABILITY and break every client that
    does not implement elicitation.
    """
    sent = []

    async def fake_send(session, invoice_id, **kwargs):
        sent.append(invoice_id)
        return {"success": True, "invoice_id": invoice_id}

    monkeypatch.setattr("invoice_machine.service.email.send_invoice_email", fake_send)

    # No elicitation_callback -> the client declares no elicitation capability.
    async with Client(_server()) as client:
        result = await client.call_tool("send_invoice_email", {"invoice_id": invoice["id"]})

    assert sent == [invoice["id"]], "send should proceed when nobody can be asked"
    assert not result.is_error


@pytest.mark.asyncio
async def test_read_only_tool_is_never_gated(invoice):
    """Confirmations are scoped to the irreversible tools only."""
    seen, callback = _asked_and_answer(True)

    async with Client(_server(), elicitation_callback=callback) as client:
        result = await client.call_tool("list_invoices", {})

    assert seen == [], "a read-only tool must not prompt"
    assert not result.is_error
