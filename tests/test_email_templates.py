"""Tests for email templates feature.

This test module covers:
- Template expansion function (expand_template)
- Email templates API endpoints (GET/PUT /api/settings/email-templates, POST /api/invoices/{id}/email-preview)
- MCP tools (get_email_templates, update_email_templates, preview_invoice_email)
- Security (authentication, validation, input handling)

Note: API endpoint, MCP tool, and some security tests require Python 3.10+ due to
the codebase's use of union type syntax (e.g., `Decimal | str`). These tests are
marked with @pytest.mark.skipif for Python 3.9 compatibility.
"""

import sys
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from invoice_machine.database import Base, BusinessProfile, Client, Invoice
from invoice_machine.email import (
    expand_template,
    DEFAULT_SUBJECT_TEMPLATE,
    DEFAULT_BODY_TEMPLATE,
)

# Skip marker for tests requiring Python 3.10+ (due to codebase using union type syntax)
requires_python_310 = pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="Requires Python 3.10+ (codebase uses union type syntax)"
)


# ============================================================================
# Template Expansion Tests
# ============================================================================


class TestTemplateExpansion:
    """Tests for expand_template() function."""

    @pytest.mark.asyncio
    async def test_expand_invoice_number(self, business_profile, invoice_with_client):
        """Invoice number placeholder is expanded."""
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
        """Document type shows 'Invoice' for invoices."""
        template = "Type: {document_type}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "Type: Invoice"

    @pytest.mark.asyncio
    async def test_expand_document_type_quote(self, business_profile, quote_with_client):
        """Document type shows 'Quote' for quotes."""
        template = "Type: {document_type}"
        result = expand_template(template, quote_with_client, business_profile)
        assert result == "Type: Quote"

    @pytest.mark.asyncio
    async def test_expand_document_type_lower(self, business_profile, invoice_with_client):
        """Document type lower shows lowercase version."""
        template = "attached {document_type_lower}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "attached invoice"

    @pytest.mark.asyncio
    async def test_expand_client_name(self, business_profile, invoice_with_client):
        """Client name placeholder is expanded."""
        template = "Dear {client_name},"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "Dear John Doe,"

    @pytest.mark.asyncio
    async def test_expand_client_business_name(self, business_profile, invoice_with_client):
        """Client business name placeholder is expanded."""
        template = "For: {client_business_name}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "For: Acme Corp"

    @pytest.mark.asyncio
    async def test_expand_client_email(self, business_profile, invoice_with_client):
        """Client email placeholder is expanded."""
        template = "Email: {client_email}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "Email: john@acme.com"

    @pytest.mark.asyncio
    async def test_expand_total_formatting(self, business_profile, invoice_with_client):
        """Total is formatted with currency."""
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
        """Subtotal is formatted with currency."""
        template = "Subtotal: {subtotal}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert "$100.00" in result

    @pytest.mark.asyncio
    async def test_expand_due_date_formatting(self, business_profile, invoice_with_client):
        """Due date is formatted as 'Month DD, YYYY'."""
        template = "Due: {due_date}"
        result = expand_template(template, invoice_with_client, business_profile)
        # Should contain month name and year
        assert "20" in result  # Year
        assert "Due:" in result

    @pytest.mark.asyncio
    async def test_expand_issue_date_formatting(self, business_profile, invoice_with_client):
        """Issue date is formatted as 'Month DD, YYYY'."""
        template = "Issued: {issue_date}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert "20" in result  # Year

    @pytest.mark.asyncio
    async def test_expand_your_name(self, business_profile, invoice_with_client):
        """Your name from profile is expanded."""
        template = "Regards, {your_name}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "Regards, Test User"

    @pytest.mark.asyncio
    async def test_expand_business_name(self, business_profile, invoice_with_client):
        """Business name from profile is expanded."""
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

    # Edge cases

    @pytest.mark.asyncio
    async def test_expand_missing_client_name_uses_default(
        self, db_session, business_profile
    ):
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
    async def test_expand_missing_due_date_shows_upon_receipt(
        self, db_session, business_profile
    ):
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
        """Unknown placeholders are left unchanged."""
        template = "Value: {unknown_placeholder}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "Value: {unknown_placeholder}"

    @pytest.mark.asyncio
    async def test_expand_empty_template(self, business_profile, invoice_with_client):
        """Empty template returns empty string."""
        result = expand_template("", invoice_with_client, business_profile)
        assert result == ""

    @pytest.mark.asyncio
    async def test_expand_template_with_no_placeholders(
        self, business_profile, invoice_with_client
    ):
        """Template with no placeholders is returned unchanged."""
        template = "This is a plain message with no variables."
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == template

    @pytest.mark.asyncio
    async def test_expand_multiple_same_placeholder(
        self, business_profile, invoice_with_client
    ):
        """Multiple instances of same placeholder are all expanded."""
        template = "{invoice_number} - {invoice_number}"
        result = expand_template(template, invoice_with_client, business_profile)
        assert result == "20250120-1 - 20250120-1"

    @pytest.mark.asyncio
    async def test_default_subject_template_expands(
        self, business_profile, invoice_with_client
    ):
        """Default subject template expands correctly."""
        result = expand_template(
            DEFAULT_SUBJECT_TEMPLATE, invoice_with_client, business_profile
        )
        assert "Invoice" in result
        assert "20250120-1" in result

    @pytest.mark.asyncio
    async def test_default_body_template_expands(
        self, business_profile, invoice_with_client
    ):
        """Default body template expands correctly."""
        result = expand_template(
            DEFAULT_BODY_TEMPLATE, invoice_with_client, business_profile
        )
        assert "John Doe" in result
        assert "20250120-1" in result
        assert "$100.00" in result
        assert "Test User" in result
        assert "services rendered" in result  # Default when no line items

    @pytest.mark.asyncio
    async def test_default_body_template_expands_line_items(
        self, business_profile, invoice_with_items
    ):
        """Default body template expands line items correctly."""
        result = expand_template(
            DEFAULT_BODY_TEMPLATE, invoice_with_items, business_profile
        )
        assert "Website Development, Logo Design" in result


# ============================================================================
# API Endpoint Tests
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def api_client():
    """Test client for HTTP requests with authentication."""
    # Import app lazily to avoid Python version issues at module level
    from invoice_machine.main import app
    from invoice_machine.api.auth import create_session, SESSION_COOKIE_NAME
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    import bcrypt

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session maker with test engine
    import invoice_machine.database

    original_maker = invoice_machine.database.async_session_maker
    invoice_machine.database.async_session_maker = async_sessionmaker(
        engine, expire_on_commit=False
    )

    # Create business profile and test user
    async with invoice_machine.database.async_session_maker() as session:
        from invoice_machine.database import User

        profile = BusinessProfile(
            id=1,
            name="Test Business",
            business_name="Test LLC",
            email="test@example.com",
        )
        session.add(profile)

        # Create test user
        password_hash = bcrypt.hashpw("testpass".encode(), bcrypt.gensalt()).decode()
        user = User(
            id=1,
            username="testuser",
            password_hash=password_hash,
        )
        session.add(user)
        await session.commit()

    # Create session token
    session_token = create_session(user_id=1)

    # Create client with session cookie
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    client.cookies.set(SESSION_COOKIE_NAME, session_token)

    yield client

    # Restore original
    invoice_machine.database.async_session_maker = original_maker
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def api_client_with_invoice(api_client):
    """API client with a test invoice created."""
    import invoice_machine.database

    async with invoice_machine.database.async_session_maker() as session:
        # Create a client first
        client = Client(
            name="API Test Client",
            business_name="API Test Corp",
            email="api@test.com",
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)

        # Create invoice
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


@requires_python_310
class TestEmailTemplatesEndpoints:
    """Tests for email templates API endpoints."""

    # GET /api/settings/email-templates

    @pytest.mark.asyncio
    async def test_get_templates_returns_defaults_when_not_set(self, api_client):
        """Returns default templates when none are set."""
        response = await api_client.get("/api/settings/email-templates")
        assert response.status_code == 200

        data = response.json()
        assert data["email_subject_template"] is None
        assert data["email_body_template"] is None
        assert "default_subject" in data
        assert "default_body" in data

    @pytest.mark.asyncio
    async def test_get_templates_includes_available_placeholders(self, api_client):
        """Returns list of available placeholders."""
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
        """Endpoint requires authentication."""
        from invoice_machine.main import app
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        response = await client.get("/api/settings/email-templates")
        assert response.status_code == 401

    # PUT /api/settings/email-templates

    @pytest.mark.asyncio
    async def test_update_subject_template(self, api_client):
        """Can update subject template."""
        response = await api_client.put(
            "/api/settings/email-templates",
            json={"email_subject_template": "Custom Subject: {invoice_number}"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["email_subject_template"] == "Custom Subject: {invoice_number}"

    @pytest.mark.asyncio
    async def test_update_body_template(self, api_client):
        """Can update body template."""
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
        """Can update both templates at once."""
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
        # First set a template
        await api_client.put(
            "/api/settings/email-templates",
            json={"email_subject_template": "Custom Subject"},
        )

        # Then clear it
        response = await api_client.put(
            "/api/settings/email-templates",
            json={"email_subject_template": ""},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["email_subject_template"] is None

    @pytest.mark.asyncio
    async def test_get_templates_returns_saved_templates(self, api_client):
        """Get returns previously saved templates."""
        # Save templates
        await api_client.put(
            "/api/settings/email-templates",
            json={
                "email_subject_template": "Saved Subject",
                "email_body_template": "Saved Body",
            },
        )

        # Get them back
        response = await api_client.get("/api/settings/email-templates")
        assert response.status_code == 200

        data = response.json()
        assert data["email_subject_template"] == "Saved Subject"
        assert data["email_body_template"] == "Saved Body"

    @pytest.mark.asyncio
    async def test_update_requires_authentication(self):
        """Update endpoint requires authentication."""
        from invoice_machine.main import app
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        response = await client.put(
            "/api/settings/email-templates",
            json={"email_subject_template": "Test"},
        )
        assert response.status_code == 401

    # POST /api/invoices/{id}/email-preview

    @pytest.mark.asyncio
    async def test_preview_with_default_templates(self, api_client_with_invoice):
        """Preview uses default templates when none saved."""
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
        """Preview uses provided custom templates."""
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
        """Preview uses saved templates when no overrides provided."""
        client, invoice_id = api_client_with_invoice

        # Save templates
        await client.put(
            "/api/settings/email-templates",
            json={
                "email_subject_template": "Saved: {invoice_number}",
                "email_body_template": "Saved body for {client_name}",
            },
        )

        # Preview without overrides should use saved
        response = await client.post(f"/api/invoices/{invoice_id}/email-preview", json={})
        assert response.status_code == 200

        data = response.json()
        assert data["subject"] == "Saved: 20250120-API"
        assert data["body"] == "Saved body for API Test Client"

    @pytest.mark.asyncio
    async def test_preview_returns_invoice_info(self, api_client_with_invoice):
        """Preview returns invoice number and recipient email."""
        client, invoice_id = api_client_with_invoice

        response = await client.post(f"/api/invoices/{invoice_id}/email-preview", json={})
        assert response.status_code == 200

        data = response.json()
        assert data["invoice_number"] == "20250120-API"
        assert data["recipient_email"] == "api@test.com"

    @pytest.mark.asyncio
    async def test_preview_invalid_invoice_returns_404(self, api_client):
        """Preview returns 404 for invalid invoice ID."""
        response = await api_client.post("/api/invoices/99999/email-preview", json={})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_preview_requires_authentication(self):
        """Preview endpoint requires authentication."""
        from invoice_machine.main import app
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        response = await client.post("/api/invoices/1/email-preview", json={})
        assert response.status_code == 401


# ============================================================================
# MCP Tool Tests (using direct function calls)
# ============================================================================


@requires_python_310
class TestEmailTemplateMCPTools:
    """Tests for email template MCP tools via direct function calls."""

    @pytest.mark.asyncio
    async def test_mcp_get_templates_structure(self, db_session, business_profile):
        """get_email_templates returns correct structure."""
        from invoice_machine.mcp.server import get_email_templates

        result = await get_email_templates()

        assert "email_subject_template" in result
        assert "email_body_template" in result
        assert "available_placeholders" in result
        assert "default_subject" in result
        assert "default_body" in result

    @pytest.mark.asyncio
    async def test_mcp_get_templates_returns_defaults(self, db_session, business_profile):
        """get_email_templates returns None when no templates set."""
        from invoice_machine.mcp.server import get_email_templates

        result = await get_email_templates()

        assert result["email_subject_template"] is None
        assert result["email_body_template"] is None
        assert "{invoice_number}" in result["available_placeholders"]

    @pytest.mark.asyncio
    async def test_mcp_update_subject_template(self, db_session, business_profile):
        """update_email_templates updates subject."""
        from invoice_machine.mcp.server import update_email_templates, get_email_templates

        result = await update_email_templates(
            email_subject_template="MCP Subject: {invoice_number}"
        )

        assert result["email_subject_template"] == "MCP Subject: {invoice_number}"

        # Verify persisted
        get_result = await get_email_templates()
        assert get_result["email_subject_template"] == "MCP Subject: {invoice_number}"

    @pytest.mark.asyncio
    async def test_mcp_update_body_template(self, db_session, business_profile):
        """update_email_templates updates body."""
        from invoice_machine.mcp.server import update_email_templates

        result = await update_email_templates(
            email_body_template="MCP Body for {client_name}"
        )

        assert result["email_body_template"] == "MCP Body for {client_name}"

    @pytest.mark.asyncio
    async def test_mcp_clear_templates(self, db_session, business_profile):
        """update_email_templates clears templates with empty string."""
        from invoice_machine.mcp.server import update_email_templates

        # Set a template
        await update_email_templates(email_subject_template="Temporary")

        # Clear it
        result = await update_email_templates(email_subject_template="")

        assert result["email_subject_template"] is None

    @pytest.mark.asyncio
    async def test_mcp_preview_with_defaults(
        self, db_session, business_profile, invoice_with_client
    ):
        """preview_invoice_email uses default templates."""
        from invoice_machine.mcp.server import preview_invoice_email

        result = await preview_invoice_email(invoice_id=invoice_with_client.id)

        assert result["invoice_id"] == invoice_with_client.id
        assert result["invoice_number"] == "20250120-1"
        assert "Invoice" in result["subject"]
        assert "John Doe" in result["body"]

    @pytest.mark.asyncio
    async def test_mcp_preview_with_overrides(
        self, db_session, business_profile, invoice_with_client
    ):
        """preview_invoice_email uses provided templates."""
        from invoice_machine.mcp.server import preview_invoice_email

        result = await preview_invoice_email(
            invoice_id=invoice_with_client.id,
            subject_template="Override: {invoice_number}",
            body_template="Override for {client_name}",
        )

        assert result["subject"] == "Override: 20250120-1"
        assert result["body"] == "Override for John Doe"

    @pytest.mark.asyncio
    async def test_mcp_preview_invalid_invoice(self, db_session, business_profile):
        """preview_invoice_email returns error for invalid invoice."""
        from invoice_machine.mcp.server import preview_invoice_email

        result = await preview_invoice_email(invoice_id=99999)

        assert "error" in result
        assert "not found" in result["error"].lower()


# ============================================================================
# Security Tests
# ============================================================================


class TestEmailTemplateSecurity:
    """Security tests for email templates."""

    @pytest.mark.asyncio
    async def test_template_expansion_handles_special_chars(
        self, db_session, business_profile
    ):
        """Template expansion handles special characters in data."""
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
        assert "<script>" in result  # Plain text email preserves this

    @requires_python_310
    @pytest.mark.asyncio
    async def test_template_api_requires_auth(self):
        """All template API endpoints require authentication."""
        from invoice_machine.main import app
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

        # GET
        response = await client.get("/api/settings/email-templates")
        assert response.status_code == 401

        # PUT
        response = await client.put(
            "/api/settings/email-templates",
            json={"email_subject_template": "test"},
        )
        assert response.status_code == 401

        # Preview
        response = await client.post("/api/invoices/1/email-preview", json={})
        assert response.status_code == 401

    @requires_python_310
    @pytest.mark.asyncio
    async def test_template_max_length_validation(self, api_client):
        """Template length is validated."""
        # Subject max is 500
        long_subject = "x" * 501
        response = await api_client.put(
            "/api/settings/email-templates",
            json={"email_subject_template": long_subject},
        )
        assert response.status_code == 422

    @requires_python_310
    @pytest.mark.asyncio
    async def test_body_template_max_length_validation(self, api_client):
        """Body template length is validated."""
        # Body max is 10000
        long_body = "x" * 10001
        response = await api_client.put(
            "/api/settings/email-templates",
            json={"email_body_template": long_body},
        )
        assert response.status_code == 422

    @requires_python_310
    @pytest.mark.asyncio
    async def test_preview_respects_max_length(self, api_client_with_invoice):
        """Preview endpoint validates template length."""
        client, invoice_id = api_client_with_invoice

        response = await client.post(
            f"/api/invoices/{invoice_id}/email-preview",
            json={"subject_template": "x" * 501},
        )
        assert response.status_code == 422
