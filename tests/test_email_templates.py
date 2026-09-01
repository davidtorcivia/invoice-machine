"""Tests for email templates feature."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from invoice_machine.database import Base, BusinessProfile, Client, Invoice
from invoice_machine.email import (
    DEFAULT_BODY_TEMPLATE,
    DEFAULT_SUBJECT_TEMPLATE,
    expand_template,
)


class TestTemplateExpansion:
    """Tests for expand_template() function."""

    @pytest.mark.asyncio
    async def test_expand_invoice_number(self, business_profile, invoice_with_client):
        template = "Invoice: {invoice_number}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "Invoice: 20250120-1"

    @pytest.mark.asyncio
    async def test_expand_quote_number(self, business_profile, quote_with_client):
        """Quote number placeholder is expanded (uses same field)."""
        template = "Quote: {quote_number}"
        result = expand_template(template, quote_with_client, business_profile)
        assert result == "Quote: Q-20250120-1"

    @pytest.mark.asyncio
    async def test_expand_document_type_invoice(self, business_profile, invoice_with_client):
        template = "Type: {document_type}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "Type: Invoice"

    @pytest.mark.asyncio
    async def test_expand_document_type_quote(self, business_profile, quote_with_client):
        template = "Type: {document_type}"
        result = expand_template(template, quote_with_client, business_profile)
        assert result == "Type: Quote"

    @pytest.mark.asyncio
    async def test_expand_document_type_lower(self, business_profile, invoice_with_client):
        template = "attached {document_type_lower}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "attached invoice"

    @pytest.mark.asyncio
    async def test_expand_client_name(self, business_profile, invoice_with_client):
        template = "Dear {client_name},"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "Dear John Doe,"

    @pytest.mark.asyncio
    async def test_expand_client_business_name(self, business_profile, invoice_with_client):
        template = "For: {client_business_name}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "For: Acme Corp"

    @pytest.mark.asyncio
    async def test_expand_client_email(self, business_profile, invoice_with_client):
        template = "Email: {client_email}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "Email: john@acme.com"

    @pytest.mark.asyncio
    async def test_expand_total_formatting(self, business_profile, invoice_with_client):
        template = "Amount: {total}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert "$100.00" in result

    @pytest.mark.asyncio
    async def test_expand_amount_alias(self, business_profile, invoice_with_client):
        """Amount alias works same as total."""
        template = "Amount: {amount}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert "$100.00" in result

    @pytest.mark.asyncio
    async def test_expand_subtotal(self, business_profile, invoice_with_client):
        template = "Subtotal: {subtotal}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert "$100.00" in result

    @pytest.mark.asyncio
    async def test_expand_due_date_formatting(self, business_profile, invoice_with_client):
        """Due date is formatted as 'Month DD, YYYY'."""
        template = "Due: {due_date}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert "20" in result
        assert "Due:" in result

    @pytest.mark.asyncio
    async def test_expand_issue_date_formatting(self, business_profile, invoice_with_client):
        """Issue date is formatted as 'Month DD, YYYY'."""
        template = "Issued: {issue_date}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert "20" in result

    @pytest.mark.asyncio
    async def test_expand_your_name(self, business_profile, invoice_with_client):
        template = "Regards, {your_name}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "Regards, Test User"

    @pytest.mark.asyncio
    async def test_expand_business_name(self, business_profile, invoice_with_client):
        template = "From: {business_name}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "From: Test Business LLC"

    @pytest.mark.asyncio
    async def test_expand_line_items_with_items(self, business_profile, invoice_with_items):
        """Line items placeholder expands to comma-separated descriptions."""
        template = "For: {line_items}"
        result = expand_template(template, invoice_with_items, business_profile)
        assert result == "For: Website Development, Logo Design"

    @pytest.mark.asyncio
    async def test_expand_line_items_empty(self, business_profile, invoice_with_client):
        """Line items placeholder defaults to 'services rendered' when no items."""
        template = "For: {line_items}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "For: services rendered"

    @pytest.mark.asyncio
    async def test_expand_missing_client_name_uses_default(self, db_session, business_profile):
        """Missing client name defaults to 'Client'."""
        invoice = Invoice(
            invoice_number="20250120-2",
            document_type="invoice",
            client_name=None,
            issue_date=date.today(),
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            currency_code="USD",
            status="draft",
        )
        db_session.add(invoice)
        await db_session.commit()

        template = "Dear {client_name},"
        result = expand_template(template, invoice, business_profile)
        assert result == "Dear Client,"

    @pytest.mark.asyncio
    async def test_expand_missing_due_date_shows_upon_receipt(self, db_session, business_profile):
        """Missing due date shows 'Upon receipt'."""
        invoice = Invoice(
            invoice_number="20250120-3",
            document_type="invoice",
            client_name="Test Client",
            issue_date=date.today(),
            due_date=None,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            currency_code="USD",
            status="draft",
        )
        db_session.add(invoice)
        await db_session.commit()

        template = "Due: {due_date}"
        result = expand_template(template, invoice, business_profile)
        assert result == "Due: Upon receipt"

    @pytest.mark.asyncio
    async def test_expand_missing_business_name_uses_personal_name(
        self, db_session, invoice_with_client
    ):
        """Missing business name falls back to personal name."""
        profile = BusinessProfile(
            id=2,
            name="Personal Name",
            business_name=None,
            email="test@example.com",
        )
        db_session.add(profile)
        await db_session.commit()

        template = "From: {business_name}"
        result = expand_template(template, invoice_with_client, profile)
        assert result == "From: Personal Name"

    @pytest.mark.asyncio
    async def test_expand_unknown_placeholder_unchanged(
        self, business_profile, invoice_with_client
    ):
        template = "Value: {unknown_placeholder}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "Value: {unknown_placeholder}"

    @pytest.mark.asyncio
    async def test_expand_empty_template(self, business_profile, invoice_with_client):
        result = expand_template("", invoice_with_client, business_profile)
        assert result == ""

    @pytest.mark.asyncio
    async def test_expand_template_with_no_placeholders(
        self, business_profile, invoice_with_client
    ):
        template = "This is a plain message with no variables."
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == template

    @pytest.mark.asyncio
    async def test_expand_multiple_same_placeholder(self, business_profile, invoice_with_client):
        template = "{invoice_number} - {invoice_number}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "20250120-1 - 20250120-1"

    @pytest.mark.asyncio
    async def test_default_subject_template_expands(self, business_profile, invoice_with_client):
        result = expand_template(DEFAULT_SUBJECT_TEMPLATE, invoice_with_client, business_profile)
        assert "Invoice" in result
        assert "20250120-1" in result

    @pytest.mark.asyncio
    async def test_default_body_template_expands(self, business_profile, invoice_with_client):
        result = expand_template(DEFAULT_BODY_TEMPLATE, invoice_with_client, business_profile)
        assert "John Doe" in result
        assert "20250120-1" in result
        assert "$100.00" in result
        assert "Test User" in result
        assert "services rendered" in result

    @pytest.mark.asyncio
    async def test_default_body_template_expands_line_items(
        self, business_profile, invoice_with_items
    ):
        result = expand_template(DEFAULT_BODY_TEMPLATE, invoice_with_items, business_profile)
        assert "Website Development, Logo Design" in result


@pytest_asyncio.fixture(scope="function")
async def api_client():
    """Test client for HTTP requests with authentication."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from invoice_machine.api.auth import SESSION_COOKIE_NAME, create_session
    from invoice_machine.main import app

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    import invoice_machine.database

    original_maker = invoice_machine.database.async_session_maker
    invoice_machine.database.async_session_maker = async_sessionmaker(
        engine, expire_on_commit=False
    )

    async with invoice_machine.database.async_session_maker() as session:
        from invoice_machine.database import User

        profile = BusinessProfile(
            id=1,
            name="Test Business",
            business_name="Test LLC",
            email="test@example.com",
        )
        session.add(profile)

        user = User(
            id=1,
            username="testuser",
            password_hash="test-password-hash",
        )
        session.add(user)
        await session.commit()

    async with invoice_machine.database.async_session_maker() as session:
        user_session = await create_session(session, user_id=1)
        session_token = user_session.cookie_token
        csrf_token = user_session.csrf_token

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    client.cookies.set(SESSION_COOKIE_NAME, session_token)
    client.headers.update({"X-CSRF-Token": csrf_token})

    yield client
    await client.aclose()

    invoice_machine.database.async_session_maker = original_maker
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def api_client_with_invoice(api_client):
    """API client with a test invoice created."""
    import invoice_machine.database

    async with invoice_machine.database.async_session_maker() as session:
        client = Client(
            name="API Test Client",
            business_name="API Test Corp",
            email="api@test.com",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)

        invoice = Invoice(
            invoice_number="20250120-API",
            document_type="invoice",
            client_id=client.id,
            client_name=client.name,
            client_business=client.business_name,
            client_email=client.email,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            subtotal=Decimal("500.00"),
            total=Decimal("500.00"),
            currency_code="USD",
            status="draft",
        )
        session.add(invoice)
        await session.commit()
        await session.refresh(invoice)

        yield api_client, invoice.id


class TestEmailTemplatesEndpoints:
    """Tests for email templates API endpoints."""

    @pytest.mark.asyncio
    async def test_get_templates_returns_defaults_when_not_set(self, api_client):
        response = await api_client.get("/api/settings/email-templates")
        assert response.status_code == 200

        data = response.json()
        assert data["email_subject_template"] is None
        assert data["email_body_template"] is None
        assert "default_subject" in data
        assert "default_body" in data

    @pytest.mark.asyncio
    async def test_get_templates_includes_available_placeholders(self, api_client):
        response = await api_client.get("/api/settings/email-templates")
        assert response.status_code == 200

        data = response.json()
        assert "available_placeholders" in data
        placeholders = data["available_placeholders"]
        assert "{invoice_number}" in placeholders
        assert "{client_name}" in placeholders
        assert "{total}" in placeholders
        assert "{due_date}" in placeholders
        assert "{line_items}" in placeholders

    @pytest.mark.asyncio
    async def test_get_templates_requires_authentication(self):
        from invoice_machine.main import app

        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        response = await client.get("/api/settings/email-templates")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_subject_template(self, api_client):
        response = await api_client.put(
            "/api/settings/email-templates",
            json={"email_subject_template": "Custom Subject: {invoice_number}"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["email_subject_template"] == "Custom Subject: {invoice_number}"

    @pytest.mark.asyncio
    async def test_update_body_template(self, api_client):
        custom_body = "Hello {client_name},\n\nYour total is {total}."
        response = await api_client.put(
            "/api/settings/email-templates",
            json={"email_body_template": custom_body},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["email_body_template"] == custom_body

    @pytest.mark.asyncio
    async def test_update_both_templates(self, api_client):
        response = await api_client.put(
            "/api/settings/email-templates",
            json={
                "email_subject_template": "Subject {invoice_number}",
                "email_body_template": "Body {client_name}",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["email_subject_template"] == "Subject {invoice_number}"
        assert data["email_body_template"] == "Body {client_name}"

    @pytest.mark.asyncio
    async def test_clear_template_with_empty_string(self, api_client):
        """Empty string clears template (uses default)."""
        await api_client.put(
            "/api/settings/email-templates",
            json={"email_subject_template": "Custom Subject"},
        )

        response = await api_client.put(
            "/api/settings/email-templates",
            json={"email_subject_template": ""},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["email_subject_template"] is None

    @pytest.mark.asyncio
    async def test_get_templates_returns_saved_templates(self, api_client):
        await api_client.put(
            "/api/settings/email-templates",
            json={
                "email_subject_template": "Saved Subject",
                "email_body_template": "Saved Body",
            },
        )

        response = await api_client.get("/api/settings/email-templates")
        assert response.status_code == 200

        data = response.json()
        assert data["email_subject_template"] == "Saved Subject"
        assert data["email_body_template"] == "Saved Body"

    @pytest.mark.asyncio
    async def test_update_requires_authentication(self):
        from invoice_machine.main import app

        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        response = await client.put(
            "/api/settings/email-templates",
            json={"email_subject_template": "Test"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_preview_with_default_templates(self, api_client_with_invoice):
        client, invoice_id = api_client_with_invoice

        response = await client.post(f"/api/invoices/{invoice_id}/email-preview", json={})
        assert response.status_code == 200

        data = response.json()
        assert data["invoice_id"] == invoice_id
        assert "Invoice" in data["subject"]
        assert "20250120-API" in data["subject"]
        assert "API Test Client" in data["body"]

    @pytest.mark.asyncio
    async def test_preview_with_custom_templates(self, api_client_with_invoice):
        client, invoice_id = api_client_with_invoice

        response = await client.post(
            f"/api/invoices/{invoice_id}/email-preview",
            json={
                "subject_template": "Custom: {invoice_number}",
                "body_template": "Hi {client_name}!",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["subject"] == "Custom: 20250120-API"
        assert data["body"] == "Hi API Test Client!"

    @pytest.mark.asyncio
    async def test_preview_with_saved_templates(self, api_client_with_invoice):
        client, invoice_id = api_client_with_invoice

        await client.put(
            "/api/settings/email-templates",
            json={
                "email_subject_template": "Saved: {invoice_number}",
                "email_body_template": "Saved body for {client_name}",
            },
        )

        response = await client.post(f"/api/invoices/{invoice_id}/email-preview", json={})
        assert response.status_code == 200

        data = response.json()
        assert data["subject"] == "Saved: 20250120-API"
        assert data["body"] == "Saved body for API Test Client"

    @pytest.mark.asyncio
    async def test_preview_returns_invoice_info(self, api_client_with_invoice):
        client, invoice_id = api_client_with_invoice

        response = await client.post(f"/api/invoices/{invoice_id}/email-preview", json={})
        assert response.status_code == 200

        data = response.json()
        assert data["invoice_number"] == "20250120-API"
        assert data["recipient_email"] == "api@test.com"

    @pytest.mark.asyncio
    async def test_preview_invalid_invoice_returns_404(self, api_client):
        response = await api_client.post("/api/invoices/99999/email-preview", json={})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_preview_requires_authentication(self):
        from invoice_machine.main import app

        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        response = await client.post("/api/invoices/1/email-preview", json={})
        assert response.status_code == 401


class TestEmailTemplateMCPTools:
    """Tests for email template MCP tools via direct function calls."""

    @pytest.fixture(autouse=True)
    async def _bind_mcp_to_test_db(self, session_maker):
        """Route MCP direct calls to the current test database session maker."""
        import invoice_machine.database
        import invoice_machine.mcp.context as mcp_context

        original_maker = invoice_machine.database.async_session_maker
        invoice_machine.database.async_session_maker = session_maker
        # Schema is already built via create_all; the mcp.context flag stops
        # get_session() running real migrations against the production database.
        original_initialized = mcp_context._schema_initialized
        mcp_context._schema_initialized = True
        try:
            yield
        finally:
            invoice_machine.database.async_session_maker = original_maker
            mcp_context._schema_initialized = original_initialized

    @pytest.mark.asyncio
    async def test_mcp_get_templates_structure(self, db_session, business_profile):
        from invoice_machine.mcp.email_tools import get_email_templates

        result = await get_email_templates()

        assert "email_subject_template" in result
        assert "email_body_template" in result
        assert "available_placeholders" in result
        assert "default_subject" in result
        assert "default_body" in result

    @pytest.mark.asyncio
    async def test_mcp_get_templates_returns_defaults(self, db_session, business_profile):
        from invoice_machine.mcp.email_tools import get_email_templates

        result = await get_email_templates()

        assert result["email_subject_template"] is None
        assert result["email_body_template"] is None
        assert "{invoice_number}" in result["available_placeholders"]

    @pytest.mark.asyncio
    async def test_mcp_update_subject_template(self, db_session, business_profile):
        from invoice_machine.mcp.email_tools import get_email_templates, update_email_templates

        result = await update_email_templates(
            email_subject_template="MCP Subject: {invoice_number}"
        )

        assert result["email_subject_template"] == "MCP Subject: {invoice_number}"

        get_result = await get_email_templates()
        assert get_result["email_subject_template"] == "MCP Subject: {invoice_number}"

    @pytest.mark.asyncio
    async def test_mcp_update_body_template(self, db_session, business_profile):
        from invoice_machine.mcp.email_tools import update_email_templates

        result = await update_email_templates(email_body_template="MCP Body for {client_name}")

        assert result["email_body_template"] == "MCP Body for {client_name}"

    @pytest.mark.asyncio
    async def test_mcp_clear_templates(self, db_session, business_profile):
        """update_email_templates clears templates with empty string."""
        from invoice_machine.mcp.email_tools import update_email_templates

        await update_email_templates(email_subject_template="Temporary")

        result = await update_email_templates(email_subject_template="")

        assert result["email_subject_template"] is None

    @pytest.mark.asyncio
    async def test_mcp_preview_with_defaults(
        self, db_session, business_profile, invoice_with_client
    ):
        from invoice_machine.mcp.email_tools import preview_invoice_email

        result = await preview_invoice_email(invoice_id=invoice_with_client.id)

        assert result["invoice_id"] == invoice_with_client.id
        assert result["invoice_number"] == "20250120-1"
        assert "Invoice" in result["subject"]
        assert "John Doe" in result["body"]

    @pytest.mark.asyncio
    async def test_mcp_preview_with_overrides(
        self, db_session, business_profile, invoice_with_client
    ):
        from invoice_machine.mcp.email_tools import preview_invoice_email

        result = await preview_invoice_email(
            invoice_id=invoice_with_client.id,
            subject_template="Override: {invoice_number}",
            body_template="Override for {client_name}",
        )

        assert result["subject"] == "Override: 20250120-1"
        assert result["body"] == "Override for John Doe"

    @pytest.mark.asyncio
    async def test_mcp_preview_invalid_invoice(self, db_session, business_profile):
        from invoice_machine.mcp.email_tools import preview_invoice_email

        result = await preview_invoice_email(invoice_id=99999)

        assert "error" in result
        assert "not found" in result["error"].lower()


class TestEmailTemplateSecurity:
    """Security tests for email templates."""

    @pytest.mark.asyncio
    async def test_template_expansion_handles_special_chars(self, db_session, business_profile):
        invoice = Invoice(
            invoice_number="20250120-SEC",
            document_type="invoice",
            client_name="O'Reilly & Sons <script>alert('xss')</script>",
            issue_date=date.today(),
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            currency_code="USD",
            status="draft",
        )
        db_session.add(invoice)
        await db_session.commit()

        template = "Client: {client_name}"
        result = expand_template(template, invoice, business_profile)

        # Should contain the raw string (emails are plain text, not HTML)
        assert "O'Reilly & Sons" in result
        assert "<script>" in result

    @pytest.mark.asyncio
    async def test_template_api_requires_auth(self):
        """All template API endpoints require authentication."""
        from invoice_machine.main import app

        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

        response = await client.get("/api/settings/email-templates")
        assert response.status_code == 401

        response = await client.put(
            "/api/settings/email-templates",
            json={"email_subject_template": "test"},
        )
        assert response.status_code == 401

        response = await client.post("/api/invoices/1/email-preview", json={})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_template_max_length_validation(self, api_client):
        # Subject max is 500
        long_subject = "x" * 501
        response = await api_client.put(
            "/api/settings/email-templates",
            json={"email_subject_template": long_subject},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_body_template_max_length_validation(self, api_client):
        # Body max is 10000
        long_body = "x" * 10001
        response = await api_client.put(
            "/api/settings/email-templates",
            json={"email_body_template": long_body},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_preview_respects_max_length(self, api_client_with_invoice):
        client, invoice_id = api_client_with_invoice

        response = await client.post(
            f"/api/invoices/{invoice_id}/email-preview",
            json={"subject_template": "x" * 501},
        )
        assert response.status_code == 422
