"""Tests for PDF generation functionality.

These tests verify:
- PDF file creation and output
- Logo embedding and path traversal protection
- Payment instructions rendering
- Invoice data formatting
- Edge cases (missing logo, long invoice numbers, tax handling)
"""

import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from invoice_machine.database import Invoice, InvoiceItem, BusinessProfile
from invoice_machine.pdf.generator import (
    format_money,
    get_logo_base64,
    generate_pdf,
    strftime_filter,
    zfill_filter,
)


class TestFormatMoney:
    """Tests for currency formatting."""

    def test_format_usd(self):
        """Format USD amounts correctly."""
        assert format_money(100, "USD") == "$100.00"
        assert format_money(1234.56, "USD") == "$1,234.56"
        assert format_money("99.99", "USD") == "$99.99"

    def test_format_other_currencies(self):
        """Format non-USD currencies correctly."""
        assert format_money(100, "EUR") == "100.00 EUR"
        assert format_money(1000, "GBP") == "1,000.00 GBP"

    def test_format_decimal(self):
        """Format Decimal amounts correctly."""
        assert format_money(Decimal("1234.56"), "USD") == "$1,234.56"

    def test_format_large_amounts(self):
        """Format large amounts with proper comma separation."""
        assert format_money(1000000, "USD") == "$1,000,000.00"

    def test_format_zero(self):
        """Format zero amounts correctly."""
        assert format_money(0, "USD") == "$0.00"

    def test_format_negative(self):
        """Format negative amounts correctly."""
        assert format_money(-100, "USD") == "$-100.00"


class TestFilters:
    """Tests for Jinja2 template filters."""

    def test_strftime_filter_date(self):
        """Format date objects correctly."""
        test_date = date(2025, 1, 15)
        assert strftime_filter(test_date, "%m/%d/%y") == "01/15/25"
        assert strftime_filter(test_date, "%B %d, %Y") == "January 15, 2025"

    def test_strftime_filter_none(self):
        """Handle None values."""
        assert strftime_filter(None) == ""

    def test_strftime_filter_string(self):
        """Handle string values."""
        assert strftime_filter("2025-01-15") == "2025-01-15"

    def test_zfill_filter(self):
        """Pad values with zeros correctly."""
        assert zfill_filter(5, 3) == "005"
        assert zfill_filter(123, 5) == "00123"
        assert zfill_filter("42", 4) == "0042"


class TestGetLogoBase64:
    """Tests for logo loading and path traversal protection."""

    def test_get_logo_base64_no_path(self):
        """Return None when no logo path set."""
        profile = MagicMock(spec=BusinessProfile)
        profile.logo_path = None
        assert get_logo_base64(profile) is None

    def test_get_logo_base64_path_traversal_slash(self):
        """Reject paths with forward slashes."""
        profile = MagicMock(spec=BusinessProfile)
        profile.logo_path = "../etc/passwd"
        assert get_logo_base64(profile) is None

    def test_get_logo_base64_path_traversal_backslash(self):
        """Reject paths with backslashes."""
        profile = MagicMock(spec=BusinessProfile)
        profile.logo_path = "..\\windows\\system.ini"
        assert get_logo_base64(profile) is None

    def test_get_logo_base64_path_traversal_dotdot(self):
        """Reject paths with parent directory references."""
        profile = MagicMock(spec=BusinessProfile)
        profile.logo_path = "..logo.png"
        assert get_logo_base64(profile) is None

    def test_get_logo_base64_nonexistent(self):
        """Return None when logo file doesn't exist."""
        profile = MagicMock(spec=BusinessProfile)
        profile.logo_path = "nonexistent.png"

        with patch("invoice_machine.pdf.generator.settings") as mock_settings:
            mock_settings.logo_dir = Path(tempfile.gettempdir())
            assert get_logo_base64(profile) is None

    def test_get_logo_base64_valid_file(self):
        """Successfully load and encode a valid logo file."""
        profile = MagicMock(spec=BusinessProfile)
        profile.logo_path = "test_logo.png"

        # Create a temporary logo file
        with tempfile.TemporaryDirectory() as tmpdir:
            logo_dir = Path(tmpdir)
            logo_file = logo_dir / "test_logo.png"
            logo_file.write_bytes(b"PNG fake image data")

            with patch("invoice_machine.pdf.generator.settings") as mock_settings:
                mock_settings.logo_dir = logo_dir
                result = get_logo_base64(profile)

                assert result is not None
                # Verify it's valid base64
                import base64
                decoded = base64.b64decode(result)
                assert decoded == b"PNG fake image data"


class TestGeneratePDF:
    """Tests for PDF generation."""

    @pytest.fixture
    def mock_invoice(self):
        """Create a mock invoice for testing."""
        invoice = MagicMock(spec=Invoice)
        invoice.id = 1
        invoice.invoice_number = "20250115-1"
        invoice.document_type = "invoice"
        invoice.client_name = "Test Client"
        invoice.client_business = "Test Corp"
        invoice.client_email = "test@example.com"
        invoice.issue_date = date(2025, 1, 15)
        invoice.due_date = date(2025, 2, 15)
        invoice.subtotal = Decimal("1000.00")
        invoice.total = Decimal("1000.00")
        invoice.currency_code = "USD"
        invoice.status = "draft"
        invoice.notes = "Test notes"
        invoice.tax_enabled = 0
        invoice.tax_rate = Decimal("0.00")
        invoice.tax_amount = Decimal("0.00")
        invoice.tax_name = "Tax"
        invoice.show_payment_instructions = True
        invoice.selected_payment_methods = None
        return invoice

    @pytest.fixture
    def mock_business_profile(self):
        """Create a mock business profile for testing."""
        profile = MagicMock(spec=BusinessProfile)
        profile.name = "Test Business"
        profile.business_name = "Test LLC"
        profile.address_line1 = "123 Test St"
        profile.city = "Test City"
        profile.state = "TS"
        profile.postal_code = "12345"
        profile.country = "United States"
        profile.email = "business@example.com"
        profile.phone = "555-1234"
        profile.logo_path = None
        profile.accent_color = "#0891b2"
        profile.default_payment_instructions = "Pay to Bank Account 12345"
        profile.payment_methods = None
        return profile

    @pytest.mark.asyncio
    async def test_generate_pdf_creates_file(
        self, mock_invoice, mock_business_profile, db_session
    ):
        """PDF generation creates a file on disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_dir = Path(tmpdir)

            with patch("invoice_machine.pdf.generator.settings") as mock_settings:
                mock_settings.pdf_dir = pdf_dir
                mock_settings.logo_dir = pdf_dir

                with patch(
                    "invoice_machine.pdf.generator.BusinessProfile.get_or_create",
                    new_callable=AsyncMock,
                    return_value=mock_business_profile,
                ):
                    with patch(
                        "invoice_machine.pdf.generator.run_in_threadpool",
                        side_effect=lambda fn, *args: fn(*args),
                    ):
                        # Mock the database query for invoice items
                        mock_result = MagicMock()
                        mock_result.scalars.return_value.all.return_value = []
                        db_session.execute = AsyncMock(return_value=mock_result)

                        result = await generate_pdf(db_session, mock_invoice)

                        assert result == "pdfs/20250115-1.pdf"
                        assert (pdf_dir / "20250115-1.pdf").exists()

    @pytest.mark.asyncio
    async def test_generate_pdf_with_items(
        self, mock_invoice, mock_business_profile, db_session
    ):
        """PDF generation includes line items."""
        mock_items = [
            MagicMock(
                spec=InvoiceItem,
                description="Web Development",
                quantity=10,
                unit_type="hours",
                unit_price=Decimal("100.00"),
                total=Decimal("1000.00"),
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_dir = Path(tmpdir)

            with patch("invoice_machine.pdf.generator.settings") as mock_settings:
                mock_settings.pdf_dir = pdf_dir
                mock_settings.logo_dir = pdf_dir

                with patch(
                    "invoice_machine.pdf.generator.BusinessProfile.get_or_create",
                    new_callable=AsyncMock,
                    return_value=mock_business_profile,
                ):
                    with patch(
                        "invoice_machine.pdf.generator.run_in_threadpool",
                        side_effect=lambda fn, *args: fn(*args),
                    ):
                        mock_result = MagicMock()
                        mock_result.scalars.return_value.all.return_value = mock_items
                        db_session.execute = AsyncMock(return_value=mock_result)

                        result = await generate_pdf(db_session, mock_invoice)

                        assert result == "pdfs/20250115-1.pdf"
                        pdf_file = pdf_dir / "20250115-1.pdf"
                        assert pdf_file.exists()
                        # Verify PDF has content
                        assert pdf_file.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_generate_pdf_with_tax(
        self, mock_invoice, mock_business_profile, db_session
    ):
        """PDF generation handles tax correctly."""
        mock_invoice.tax_enabled = 1
        mock_invoice.tax_rate = Decimal("8.25")
        mock_invoice.tax_amount = Decimal("82.50")
        mock_invoice.tax_name = "Sales Tax"
        mock_invoice.total = Decimal("1082.50")

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_dir = Path(tmpdir)

            with patch("invoice_machine.pdf.generator.settings") as mock_settings:
                mock_settings.pdf_dir = pdf_dir
                mock_settings.logo_dir = pdf_dir

                with patch(
                    "invoice_machine.pdf.generator.BusinessProfile.get_or_create",
                    new_callable=AsyncMock,
                    return_value=mock_business_profile,
                ):
                    with patch(
                        "invoice_machine.pdf.generator.run_in_threadpool",
                        side_effect=lambda fn, *args: fn(*args),
                    ):
                        mock_result = MagicMock()
                        mock_result.scalars.return_value.all.return_value = []
                        db_session.execute = AsyncMock(return_value=mock_result)

                        result = await generate_pdf(db_session, mock_invoice)

                        assert result == "pdfs/20250115-1.pdf"

    @pytest.mark.asyncio
    async def test_generate_pdf_quote(
        self, mock_invoice, mock_business_profile, db_session
    ):
        """PDF generation works for quotes."""
        mock_invoice.document_type = "quote"
        mock_invoice.invoice_number = "Q-20250115-1"

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_dir = Path(tmpdir)

            with patch("invoice_machine.pdf.generator.settings") as mock_settings:
                mock_settings.pdf_dir = pdf_dir
                mock_settings.logo_dir = pdf_dir

                with patch(
                    "invoice_machine.pdf.generator.BusinessProfile.get_or_create",
                    new_callable=AsyncMock,
                    return_value=mock_business_profile,
                ):
                    with patch(
                        "invoice_machine.pdf.generator.run_in_threadpool",
                        side_effect=lambda fn, *args: fn(*args),
                    ):
                        mock_result = MagicMock()
                        mock_result.scalars.return_value.all.return_value = []
                        db_session.execute = AsyncMock(return_value=mock_result)

                        result = await generate_pdf(db_session, mock_invoice)

                        assert result == "pdfs/Q-20250115-1.pdf"

    @pytest.mark.asyncio
    async def test_generate_pdf_with_payment_methods(
        self, mock_invoice, mock_business_profile, db_session
    ):
        """PDF generation includes selected payment methods."""
        mock_invoice.selected_payment_methods = '["pm-1", "pm-2"]'
        mock_business_profile.payment_methods = (
            '[{"id": "pm-1", "name": "Bank Transfer", "instructions": "Account: 12345"}, '
            '{"id": "pm-2", "name": "Venmo", "instructions": "@mybusiness"}]'
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_dir = Path(tmpdir)

            with patch("invoice_machine.pdf.generator.settings") as mock_settings:
                mock_settings.pdf_dir = pdf_dir
                mock_settings.logo_dir = pdf_dir

                with patch(
                    "invoice_machine.pdf.generator.BusinessProfile.get_or_create",
                    new_callable=AsyncMock,
                    return_value=mock_business_profile,
                ):
                    with patch(
                        "invoice_machine.pdf.generator.run_in_threadpool",
                        side_effect=lambda fn, *args: fn(*args),
                    ):
                        mock_result = MagicMock()
                        mock_result.scalars.return_value.all.return_value = []
                        db_session.execute = AsyncMock(return_value=mock_result)

                        result = await generate_pdf(db_session, mock_invoice)

                        assert result == "pdfs/20250115-1.pdf"

    @pytest.mark.asyncio
    async def test_generate_pdf_long_invoice_number(
        self, mock_invoice, mock_business_profile, db_session
    ):
        """PDF generation handles long invoice numbers."""
        mock_invoice.invoice_number = "INV-20250115-SPECIAL-CLIENT-12345"

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_dir = Path(tmpdir)

            with patch("invoice_machine.pdf.generator.settings") as mock_settings:
                mock_settings.pdf_dir = pdf_dir
                mock_settings.logo_dir = pdf_dir

                with patch(
                    "invoice_machine.pdf.generator.BusinessProfile.get_or_create",
                    new_callable=AsyncMock,
                    return_value=mock_business_profile,
                ):
                    with patch(
                        "invoice_machine.pdf.generator.run_in_threadpool",
                        side_effect=lambda fn, *args: fn(*args),
                    ):
                        mock_result = MagicMock()
                        mock_result.scalars.return_value.all.return_value = []
                        db_session.execute = AsyncMock(return_value=mock_result)

                        result = await generate_pdf(db_session, mock_invoice)

                        assert "INV-20250115-SPECIAL-CLIENT-12345.pdf" in result


class TestPDFTemplate:
    """Tests for PDF template rendering."""

    def test_template_exists(self):
        """Verify the HTML template file exists."""
        template_path = Path(__file__).parent.parent / "invoice_machine" / "pdf" / "template.html"
        assert template_path.exists(), "PDF template file should exist"

    def test_template_has_required_elements(self):
        """Verify template contains required elements."""
        template_path = Path(__file__).parent.parent / "invoice_machine" / "pdf" / "template.html"
        content = template_path.read_text()

        # Check for required template variables
        assert "{{ invoice.invoice_number }}" in content or "invoice_number" in content
        assert "{{ business.name }}" in content or "business.name" in content
        assert "format_money" in content
