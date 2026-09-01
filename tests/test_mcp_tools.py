"""MCP tool-layer tests.

These call the decorated tool functions directly against a temp DB, exercising
the same code paths Claude Desktop / the bot would.
"""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from invoice_machine.mcp import (
    analytics_tools,
    client_tools,
    email_tools,
    invoice_tools,
    profile_tools,
    recurring_tools,
    search_tools,
)
from invoice_machine.mcp.confirmations import Confirmation


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

    item = await invoice_tools.add_invoice_item(
        invoice_id, "Consulting", quantity=1.5, unit_price=100, unit_type="hours"
    )
    assert item["quantity"] == "1.5"
    assert item["total"] == "150.00"

    full = await invoice_tools.get_invoice(invoice_id)
    assert full["total"] == "250.00"


@pytest.mark.asyncio
async def test_invoice_create_inherits_business_tax_default(mcp_db):
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
    with pytest.raises(ToolError):
        await profile_tools.update_business_profile(accent_color="red}*{x:url(file:///etc/passwd)}")

    ok = await profile_tools.update_business_profile(accent_color="#0891b2")
    assert ok["accent_color"] == "#0891b2"


@pytest.mark.asyncio
async def test_list_invoices_document_type_filter(mcp_db):
    client = await client_tools.create_client(name="Mixed")
    await invoice_tools.create_invoice(
        client_id=client["id"],
        document_type="invoice",
        items=[{"description": "inv", "quantity": 1, "unit_price": 10}],
    )
    await invoice_tools.create_invoice(
        client_id=client["id"],
        document_type="quote",
        items=[{"description": "quo", "quantity": 1, "unit_price": 20}],
    )

    quotes = await invoice_tools.list_invoices(document_type="quote")
    assert len(quotes) == 1
    assert quotes[0]["document_type"] == "quote"


@pytest.mark.asyncio
async def test_recurring_schedule_validates_items(mcp_db):
    client = await client_tools.create_client(name="Retainer")
    # A bad unit_price must be rejected at save time, not at generation time.
    with pytest.raises(ToolError):
        await recurring_tools.create_recurring_schedule(
            client_id=client["id"],
            name="Bad",
            frequency="monthly",
            items=[{"description": "x", "quantity": 1, "unit_price": "not-a-number"}],
        )

    good = await recurring_tools.create_recurring_schedule(
        client_id=client["id"],
        name="Good",
        frequency="monthly",
        schedule_day=15,
        items=[{"description": "Retainer", "quantity": 1, "unit_price": 500}],
    )
    # Calling the tool directly bypasses the MCP layer that would resolve the
    # confirmation by asking the client, so supply it.
    triggered = await recurring_tools.trigger_recurring_schedule(
        good["id"], Confirmation(confirm=True)
    )
    assert triggered["success"] is True


@pytest.mark.asyncio
async def test_client_invoice_context_excludes_quotes_and_scopes_currency(mcp_db):
    client = await client_tools.create_client(name="Ctx")
    inv = await invoice_tools.create_invoice(
        client_id=client["id"],
        document_type="invoice",
        items=[{"description": "billed", "quantity": 1, "unit_price": 300}],
    )
    await invoice_tools.update_invoice(inv["id"], status="sent")
    await invoice_tools.create_invoice(
        client_id=client["id"],
        document_type="quote",
        items=[{"description": "quote", "quantity": 1, "unit_price": 999}],
    )

    ctx = await analytics_tools.get_client_invoice_context(client["id"])
    assert ctx["statistics"]["total_billed"] == "300.00"


@pytest.mark.asyncio
async def test_email_templates_roundtrip_and_search(mcp_db):
    updated = await email_tools.update_email_templates(email_subject_template="Hi {client_name}")
    assert updated["email_subject_template"] == "Hi {client_name}"

    await client_tools.create_client(name="Searchable Co", business_name="Searchable Co")
    results = await search_tools.search("Searchable")
    assert any(
        "Searchable" in (c.get("business_name") or c.get("name") or "") for c in results["clients"]
    )


@pytest.mark.asyncio
async def test_missing_records_raise_tool_errors(mcp_db):
    from invoice_machine.mcp import analytics_tools, document_tools, export_tools

    with pytest.raises(ToolError, match="Invoice 99999 not found"):
        await document_tools.generate_pdf(99999)
    with pytest.raises(ToolError, match="Client 99999 not found"):
        await analytics_tools.get_client_invoice_context(99999)
    with pytest.raises(ToolError, match="Unknown export kind"):
        await export_tools.export_csv(kind="bogus")
    with pytest.raises(ToolError, match="Invoice 99999 not found"):
        await invoice_tools.add_invoice_item(99999, "x", 1, 1)
    with pytest.raises(ToolError, match="Invoice 99999 not found"):
        await email_tools.send_invoice_email(99999, Confirmation(confirm=True))
    with pytest.raises(ToolError, match="Schedule 99999 not found"):
        await recurring_tools.trigger_recurring_schedule(99999, Confirmation(confirm=True))


@pytest.mark.asyncio
async def test_service_validation_errors_reach_the_client_as_tool_errors(mcp_db):
    from invoice_machine.mcp import payment_tools

    client = await client_tools.create_client(name="Quoted")
    quote = await invoice_tools.create_invoice(
        client_id=client["id"],
        document_type="quote",
        items=[{"description": "x", "quantity": 1, "unit_price": "10"}],
    )
    with pytest.raises(ToolError, match="quote"):
        await payment_tools.record_payment(quote["id"], amount="10.00", idempotency_key="k-1")


@pytest.mark.asyncio
async def test_recurring_schedule_lifecycle(mcp_db):
    client = await client_tools.create_client(name="Retainer")
    created = await recurring_tools.create_recurring_schedule(
        client_id=client["id"],
        name="Monthly",
        frequency="monthly",
        schedule_day=1,
        items=[{"description": "Retainer", "quantity": 1, "unit_price": 500}],
    )
    sid = created["id"]

    assert [s["id"] for s in await recurring_tools.list_recurring_schedules()] == [sid]
    assert (await recurring_tools.get_recurring_schedule(sid))["name"] == "Monthly"
    assert await recurring_tools.get_recurring_schedule(99999) is None

    updated = await recurring_tools.update_recurring_schedule(
        sid,
        name="Monthly v2",
        payment_terms_days=14,
        notes="n",
        use_default_notes=False,
        items=[{"description": "Retainer", "quantity": 2, "unit_price": 250}],
        next_invoice_date="2030-01-01",
        show_payment_instructions=True,
        auto_email_enabled=False,
        tax_enabled=True,
        tax_rate=8.5,
        tax_name="VAT",
    )
    assert updated["name"] == "Monthly v2"
    assert updated["payment_terms_days"] == 14
    assert updated["next_invoice_date"] == "2030-01-01"
    assert await recurring_tools.update_recurring_schedule(99999, name="x") is None

    assert await recurring_tools.pause_recurring_schedule(sid) is True
    assert (await recurring_tools.get_recurring_schedule(sid))["is_active"] in (0, False)
    assert await recurring_tools.resume_recurring_schedule(sid) is True
    assert await recurring_tools.delete_recurring_schedule(sid) is True
    assert await recurring_tools.list_recurring_schedules() == []


@pytest.mark.asyncio
async def test_list_trash_and_generate_pdf(mcp_db, monkeypatch):
    from invoice_machine.mcp import document_tools

    client = await client_tools.create_client(name="Trashed Co")
    invoice = await invoice_tools.create_invoice(
        client_id=client["id"],
        items=[{"description": "x", "quantity": 1, "unit_price": "10"}],
    )

    async def fake_render(session, inv):
        return "fake.pdf"

    monkeypatch.setattr("invoice_machine.pdf.generator.generate_pdf", fake_render)
    result = await document_tools.generate_pdf(invoice["id"])
    assert result["invoice_id"] == invoice["id"]
    assert result["pdf_url"].endswith(f"/api/invoices/{invoice['id']}/pdf")
    assert result["generated_at"]

    other = await client_tools.create_client(name="Gone Co")
    assert await invoice_tools.delete_invoice(invoice["id"]) is True
    assert await client_tools.delete_client(other["id"]) is True

    trash = await document_tools.list_trash()
    kinds = {(t["type"], t["id"]) for t in trash}
    assert ("invoice", invoice["id"]) in kinds
    assert ("client", other["id"]) in kinds
    assert all("days_until_purge" in t for t in trash)


@pytest.mark.asyncio
async def test_bearer_auth_wrapper(monkeypatch):
    from invoice_machine.mcp.server import BearerAuth

    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b""}

    app = BearerAuth(inner)
    await app({"type": "lifespan"}, receive, send)
    assert seen == ["lifespan"]

    async def deny(request):
        return False

    monkeypatch.setattr("invoice_machine.api.mcp.verify_mcp_auth", deny)
    scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": [], "query_string": b""}
    await app(scope, receive, send)
    assert sent[0]["status"] == 401
    assert seen == ["lifespan"]

    async def allow(request):
        return True

    monkeypatch.setattr("invoice_machine.api.mcp.verify_mcp_auth", allow)
    await app(scope, receive, send)
    assert seen == ["lifespan", "http"]


@pytest.mark.asyncio
async def test_schema_bootstrap_runs_once(monkeypatch):
    from invoice_machine.mcp import context

    calls = []

    async def fake_ensure(*, apply_migrations):
        calls.append(apply_migrations)

    monkeypatch.setattr(context, "ensure_database_schema", fake_ensure)
    monkeypatch.setattr(context, "_schema_initialized", False)
    await context.ensure_mcp_schema_initialized()
    await context.ensure_mcp_schema_initialized()
    assert calls == [True]


def test_main_runs_the_stdio_transport(monkeypatch):
    from unittest.mock import MagicMock

    from invoice_machine.mcp import server

    run = MagicMock()
    monkeypatch.setattr(server.mcp, "run", run)
    server.main()

    assert run.called
