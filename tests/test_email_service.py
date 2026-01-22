"""Tests for email service functionality.

These tests verify:
- Email validation and sanitization
- Header injection prevention
- Template expansion
- SMTP connection and sending
- Error handling
"""

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from invoice_machine.database import Invoice, InvoiceItem, BusinessProfile
from invoice_machine.email import (
    _sanitize_email,
    _sanitize_header,
    expand_template,
    EmailService,
    DEFAULT_SUBJECT_TEMPLATE,
    DEFAULT_BODY_TEMPLATE,
)


class TestSanitizeEmail:
    """Tests for email validation and sanitization."""

    def test_valid_email(self):
        """Accept valid email addresses."""
        assert _sanitize_email("user@example.com") == "user@example.com"
        assert _sanitize_email("user.name@example.com") == "user.name@example.com"
        assert _sanitize_email("user+tag@example.co.uk") == "user+tag@example.co.uk"

    def test_strips_whitespace(self):
        """Strip leading/trailing whitespace."""
        assert _sanitize_email("  user@example.com  ") == "user@example.com"

    def test_rejects_empty(self):
        """Reject empty email addresses."""
        with pytest.raises(ValueError, match="required"):
            _sanitize_email("")

    def test_rejects_newline_injection(self):
        """Reject email addresses with newline characters."""
        with pytest.raises(ValueError, match="newline"):
            _sanitize_email("user@example.com\nBcc: attacker@evil.com")

    def test_rejects_carriage_return_injection(self):
        """Reject email addresses with carriage return characters."""
        with pytest.raises(ValueError, match="newline"):
            _sanitize_email("user@example.com\rBcc: attacker@evil.com")

    def test_rejects_invalid_format(self):
        """Reject invalid email formats."""
        with pytest.raises(ValueError, match="Invalid email address format"):
            _sanitize_email("not-an-email")

        with pytest.raises(ValueError, match="Invalid email address format"):
            _sanitize_email("@example.com")

        with pytest.raises(ValueError, match="Invalid email address format"):
            _sanitize_email("user@")


class TestSanitizeHeader:
    """Tests for header value sanitization."""

    def test_valid_header(self):
        """Accept valid header values."""
        assert _sanitize_header("Invoice 12345") == "Invoice 12345"
        assert _sanitize_header("Test Business LLC") == "Test Business LLC"

    def test_empty_header(self):
        """Handle empty header values."""
        assert _sanitize_header("") == ""
        assert _sanitize_header(None) == ""

    def test_rejects_newline_injection(self):
        """Reject headers with newline characters."""
        with pytest.raises(ValueError, match="newline"):
            _sanitize_header("Subject\nBcc: attacker@evil.com", "Subject")

    def test_rejects_carriage_return_injection(self):
        """Reject headers with carriage return characters."""
        with pytest.raises(ValueError, match="newline"):
            _sanitize_header("Subject\rBcc: attacker@evil.com", "Subject")

    def test_removes_control_characters(self):
        """Remove control characters from headers."""
        result = _sanitize_header("Test\x00Subject")
        assert "\x00" not in result

    def test_allows_tab(self):
        """Allow tab characters in headers."""
        result = _sanitize_header("Item\tDescription")
        assert "\t" in result


class TestExpandTemplate:
    """Tests for email template expansion."""

    @pytest.fixture
    def mock_invoice(self):
        """Create a mock invoice for template testing."""
        invoice = MagicMock(spec=Invoice)
        invoice.invoice_number = "20250115-1"
        invoice.document_type = "invoice"
        invoice.client_name = "John Doe"
        invoice.client_business = "Acme Corp"
        invoice.client_email = "john@acme.com"
        invoice.issue_date = date(2025, 1, 15)
        invoice.due_date = date(2025, 2, 15)
        invoice.subtotal = Decimal("1000.00")
        invoice.total = Decimal("1000.00")
        invoice.currency_code = "USD"
        invoice.items = []
        return invoice

    @pytest.fixture
    def mock_profile(self):
        """Create a mock business profile for template testing."""
        profile = MagicMock(spec=BusinessProfile)
        profile.name = "Jane Smith"
        profile.business_name = "Smith Consulting"
        return profile

    def test_expand_invoice_number(self, mock_invoice, mock_profile):
        """Expand invoice number placeholder."""
        result = expand_template("Invoice {invoice_number}", mock_invoice, mock_profile)
        assert result == "Invoice 20250115-1"

    def test_expand_quote_number(self, mock_invoice, mock_profile):
        """Expand quote number placeholder (same as invoice number)."""
        result = expand_template("Quote {quote_number}", mock_invoice, mock_profile)
        assert result == "Quote 20250115-1"

    def test_expand_document_type_invoice(self, mock_invoice, mock_profile):
        """Expand document type for invoice."""
        result = expand_template("{document_type}", mock_invoice, mock_profile)
        assert result == "Invoice"

        result = expand_template("{document_type_lower}", mock_invoice, mock_profile)
        assert result == "invoice"

    def test_expand_document_type_quote(self, mock_invoice, mock_profile):
        """Expand document type for quote."""
        mock_invoice.document_type = "quote"
        result = expand_template("{document_type}", mock_invoice, mock_profile)
        assert result == "Quote"

        result = expand_template("{document_type_lower}", mock_invoice, mock_profile)
        assert result == "quote"

    def test_expand_client_info(self, mock_invoice, mock_profile):
        """Expand client information placeholders."""
        result = expand_template("{client_name}", mock_invoice, mock_profile)
        assert result == "John Doe"

        result = expand_template("{client_business_name}", mock_invoice, mock_profile)
        assert result == "Acme Corp"

        result = expand_template("{client_email}", mock_invoice, mock_profile)
        assert result == "john@acme.com"

    def test_expand_amounts(self, mock_invoice, mock_profile):
        """Expand amount placeholders."""
        result = expand_template("{total}", mock_invoice, mock_profile)
        assert "$1,000.00" in result

        result = expand_template("{amount}", mock_invoice, mock_profile)
        assert "$1,000.00" in result

        result = expand_template("{subtotal}", mock_invoice, mock_profile)
        assert "$1,000.00" in result

    def test_expand_dates(self, mock_invoice, mock_profile):
        """Expand date placeholders."""
        result = expand_template("{due_date}", mock_invoice, mock_profile)
        assert "February 15, 2025" in result

        result = expand_template("{issue_date}", mock_invoice, mock_profile)
        assert "January 15, 2025" in result

    def test_expand_business_info(self, mock_invoice, mock_profile):
        """Expand business information placeholders."""
        result = expand_template("{your_name}", mock_invoice, mock_profile)
        assert result == "Jane Smith"

        result = expand_template("{business_name}", mock_invoice, mock_profile)
        assert result == "Smith Consulting"

    def test_expand_line_items(self, mock_invoice, mock_profile):
        """Expand line items placeholder."""
        mock_items = [
            MagicMock(description="Web Development"),
            MagicMock(description="Logo Design"),
        ]
        mock_invoice.items = mock_items

        result = expand_template("{line_items}", mock_invoice, mock_profile)
        assert "Web Development" in result
        assert "Logo Design" in result

    def test_expand_line_items_fallback(self, mock_invoice, mock_profile):
        """Fall back to default text when no line items."""
        mock_invoice.items = []

        result = expand_template("{line_items}", mock_invoice, mock_profile)
        assert result == "services rendered"

    def test_expand_missing_due_date(self, mock_invoice, mock_profile):
        """Handle missing due date."""
        mock_invoice.due_date = None

        result = expand_template("{due_date}", mock_invoice, mock_profile)
        assert result == "Upon receipt"

    def test_expand_missing_client_name(self, mock_invoice, mock_profile):
        """Handle missing client name."""
        mock_invoice.client_name = None
        mock_invoice.client_business = None

        result = expand_template("{client_name}", mock_invoice, mock_profile)
        assert result == "Client"

    def test_expand_default_subject_template(self, mock_invoice, mock_profile):
        """Expand default subject template correctly."""
        result = expand_template(DEFAULT_SUBJECT_TEMPLATE, mock_invoice, mock_profile)
        assert result == "Invoice 20250115-1"

    def test_expand_default_body_template(self, mock_invoice, mock_profile):
        """Expand default body template correctly."""
        result = expand_template(DEFAULT_BODY_TEMPLATE, mock_invoice, mock_profile)
        assert "John Doe" in result
        assert "20250115-1" in result
        assert "$1,000.00" in result


class TestEmailService:
    """Tests for EmailService class."""

    @pytest.fixture
    def mock_profile(self):
        """Create a mock business profile with SMTP settings."""
        profile = MagicMock(spec=BusinessProfile)
        profile.name = "Test Business"
        profile.business_name = "Test LLC"
        profile.smtp_enabled = True
        profile.smtp_host = "smtp.example.com"
        profile.smtp_port = 587
        profile.smtp_from_email = "invoice@test.com"
        profile.smtp_from_name = "Test Business"
        profile.smtp_username = "user@test.com"
        profile.smtp_password = "password123"
        profile.smtp_use_tls = True
        profile.email_subject_template = None
        profile.email_body_template = None
        return profile

    @pytest.fixture
    def mock_invoice(self):
        """Create a mock invoice for email testing."""
        invoice = MagicMock(spec=Invoice)
        invoice.invoice_number = "20250115-1"
        invoice.document_type = "invoice"
        invoice.client_name = "John Doe"
        invoice.client_business = "Acme Corp"
        invoice.client_email = "john@acme.com"
        invoice.issue_date = date(2025, 1, 15)
        invoice.due_date = date(2025, 2, 15)
        invoice.subtotal = Decimal("1000.00")
        invoice.total = Decimal("1000.00")
        invoice.currency_code = "USD"
        invoice.pdf_path = "pdfs/20250115-1.pdf"
        invoice.items = []
        return invoice

    def test_validate_config_smtp_disabled(self, mock_profile):
        """Raise error when SMTP is disabled."""
        mock_profile.smtp_enabled = False
        service = EmailService(mock_profile)

        with pytest.raises(ValueError, match="not enabled"):
            service._validate_config()

    def test_validate_config_missing_host(self, mock_profile):
        """Raise error when SMTP host is missing."""
        mock_profile.smtp_host = None
        service = EmailService(mock_profile)

        with pytest.raises(ValueError, match="host is not configured"):
            service._validate_config()

    def test_validate_config_missing_from_email(self, mock_profile):
        """Raise error when from email is missing."""
        mock_profile.smtp_from_email = None
        service = EmailService(mock_profile)

        with pytest.raises(ValueError, match="from email is not configured"):
            service._validate_config()

    def test_validate_config_success(self, mock_profile):
        """Validation passes with complete config."""
        service = EmailService(mock_profile)
        service._validate_config()  # Should not raise

    @pytest.mark.asyncio
    async def test_send_invoice_no_recipient(self, mock_profile, mock_invoice):
        """Return error when no recipient email available."""
        mock_invoice.client_email = None
        service = EmailService(mock_profile)

        result = await service.send_invoice(mock_invoice)

        assert result["success"] is False
        assert "No recipient email" in result["error"]

    @pytest.mark.asyncio
    async def test_send_invoice_no_pdf(self, mock_profile, mock_invoice):
        """Return error when PDF not generated."""
        mock_invoice.pdf_path = None
        service = EmailService(mock_profile)

        result = await service.send_invoice(mock_invoice)

        assert result["success"] is False
        assert "PDF not generated" in result["error"]

    @pytest.mark.asyncio
    async def test_send_invoice_pdf_not_found(self, mock_profile, mock_invoice):
        """Return error when PDF file doesn't exist."""
        service = EmailService(mock_profile)

        with patch("invoice_machine.email.settings") as mock_settings:
            mock_settings.data_dir = Path("/nonexistent")

            result = await service.send_invoice(mock_invoice)

            assert result["success"] is False
            assert "PDF not found" in result["error"]

    @pytest.mark.asyncio
    async def test_send_invoice_success(self, mock_profile, mock_invoice):
        """Successfully send an invoice email."""
        service = EmailService(mock_profile)

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            pdf_dir = data_dir / "pdfs"
            pdf_dir.mkdir()
            pdf_file = pdf_dir / "20250115-1.pdf"
            pdf_file.write_bytes(b"%PDF-1.4 fake content")

            with patch("invoice_machine.email.settings") as mock_settings:
                mock_settings.data_dir = data_dir

                with patch.object(
                    service, "_send_email_sync", return_value=True
                ):
                    with patch(
                        "invoice_machine.email.run_in_threadpool",
                        side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
                    ):
                        result = await service.send_invoice(mock_invoice)

                        assert result["success"] is True
                        assert result["recipient"] == "john@acme.com"
                        assert result["invoice_number"] == "20250115-1"

    @pytest.mark.asyncio
    async def test_send_invoice_with_override_recipient(
        self, mock_profile, mock_invoice
    ):
        """Send invoice to override recipient."""
        service = EmailService(mock_profile)

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            pdf_dir = data_dir / "pdfs"
            pdf_dir.mkdir()
            pdf_file = pdf_dir / "20250115-1.pdf"
            pdf_file.write_bytes(b"%PDF-1.4 fake content")

            with patch("invoice_machine.email.settings") as mock_settings:
                mock_settings.data_dir = data_dir

                with patch.object(
                    service, "_send_email_sync", return_value=True
                ):
                    with patch(
                        "invoice_machine.email.run_in_threadpool",
                        side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs),
                    ):
                        result = await service.send_invoice(
                            mock_invoice, recipient_email="other@example.com"
                        )

                        assert result["success"] is True
                        assert result["recipient"] == "other@example.com"

    @pytest.mark.asyncio
    async def test_send_invoice_smtp_error(self, mock_profile, mock_invoice):
        """Handle SMTP errors gracefully."""
        service = EmailService(mock_profile)

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            pdf_dir = data_dir / "pdfs"
            pdf_dir.mkdir()
            pdf_file = pdf_dir / "20250115-1.pdf"
            pdf_file.write_bytes(b"%PDF-1.4 fake content")

            with patch("invoice_machine.email.settings") as mock_settings:
                mock_settings.data_dir = data_dir

                with patch(
                    "invoice_machine.email.run_in_threadpool",
                    side_effect=Exception("SMTP connection failed"),
                ):
                    result = await service.send_invoice(mock_invoice)

                    assert result["success"] is False
                    assert "SMTP connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_test_connection_success(self, mock_profile):
        """Test SMTP connection successfully."""
        service = EmailService(mock_profile)

        with patch(
            "invoice_machine.email.run_in_threadpool",
            side_effect=lambda fn: fn(),
        ):
            with patch("smtplib.SMTP") as mock_smtp:
                mock_smtp.return_value.__enter__ = MagicMock()
                mock_smtp.return_value.__exit__ = MagicMock()

                result = await service.test_connection()

                assert result["success"] is True
                assert "Successfully connected" in result["message"]

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, mock_profile):
        """Handle connection test failure."""
        service = EmailService(mock_profile)

        with patch(
            "invoice_machine.email.run_in_threadpool",
            side_effect=Exception("Connection refused"),
        ):
            result = await service.test_connection()

            assert result["success"] is False
            assert "Connection refused" in result["error"]

    def test_get_smtp_password_encrypted(self, mock_profile):
        """Decrypt encrypted SMTP password."""
        mock_profile.smtp_password = "enc:encrypted_data"
        service = EmailService(mock_profile)

        with patch(
            "invoice_machine.email.decrypt_credential", return_value="decrypted_password"
        ):
            result = service._get_smtp_password()
            assert result == "decrypted_password"

    def test_get_smtp_password_none(self, mock_profile):
        """Handle missing SMTP password."""
        mock_profile.smtp_password = None
        service = EmailService(mock_profile)

        result = service._get_smtp_password()
        assert result is None

    def test_get_smtp_password_decryption_failure(self, mock_profile):
        """Fall back to raw value on decryption failure."""
        mock_profile.smtp_password = "plain_password"
        service = EmailService(mock_profile)

        with patch(
            "invoice_machine.email.decrypt_credential", side_effect=ValueError("Decrypt failed")
        ):
            result = service._get_smtp_password()
            assert result == "plain_password"
