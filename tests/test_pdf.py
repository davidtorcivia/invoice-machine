"""Tests for PDF generation functionality."""

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from invoice_machine.database import BusinessProfile, Invoice, InvoiceItem

try:
    from invoice_machine.pdf.generator import (
        format_money,
        generate_pdf,
        get_logo_data_uri,
        strftime_filter,
        zfill_filter,
    )
except OSError as e:
    pytest.skip(
        f"WeasyPrint dependencies missing: {e}",
        allow_module_level=True,
    )


class TestFormatMoney:
    """Tests for currency formatting."""

    def test_format_usd(self):
        assert format_money(100, "USD") == "$100.00"
        assert format_money(1234.56, "USD") == "$1,234.56"
        assert format_money("99.99", "USD") == "$99.99"

    def test_format_other_currencies(self):
        assert format_money(100, "EUR") == "100.00 EUR"
        assert format_money(1000, "GBP") == "1,000.00 GBP"

    def test_format_decimal(self):
        assert format_money(Decimal("1234.56"), "USD") == "$1,234.56"

    def test_format_large_amounts(self):
        assert format_money(1000000, "USD") == "$1,000,000.00"

    def test_format_zero(self):
        assert format_money(0, "USD") == "$0.00"

    def test_format_negative(self):
        assert format_money(-100, "USD") == "$-100.00"


class TestFilters:
    """Tests for Jinja2 template filters."""

    def test_strftime_filter_date(self):
        test_date = date(2025, 1, 15)
        assert strftime_filter(test_date, "%m/%d/%y") == "01/15/25"
        assert strftime_filter(test_date, "%B %d, %Y") == "January 15, 2025"

    def test_strftime_filter_none(self):
        assert strftime_filter(None) == ""

    def test_strftime_filter_string(self):
        assert strftime_filter("2025-01-15") == "2025-01-15"

    def test_zfill_filter(self):
        assert zfill_filter(5, 3) == "005"
        assert zfill_filter(123, 5) == "00123"
        assert zfill_filter("42", 4) == "0042"


class TestGetLogoBase64:
    """Tests for logo loading and path traversal protection."""

    def test_get_logo_data_uri_no_path(self):
        profile = MagicMock(spec=BusinessProfile)
        profile.logo_path = None
        assert get_logo_data_uri(profile) is None

    def test_get_logo_data_uri_path_traversal_slash(self):
        profile = MagicMock(spec=BusinessProfile)
        profile.logo_path = "../etc/passwd"
        assert get_logo_data_uri(profile) is None

    def test_get_logo_data_uri_path_traversal_backslash(self):
        profile = MagicMock(spec=BusinessProfile)
        profile.logo_path = "..\\windows\\system.ini"
        assert get_logo_data_uri(profile) is None

    def test_get_logo_data_uri_path_traversal_dotdot(self):
        profile = MagicMock(spec=BusinessProfile)
        profile.logo_path = "..logo.png"
        assert get_logo_data_uri(profile) is None

    def test_get_logo_data_uri_nonexistent(self):
        profile = MagicMock(spec=BusinessProfile)
        profile.logo_path = "nonexistent.png"

        with patch("invoice_machine.pdf.generator.settings") as mock_settings:
            mock_settings.logo_dir = Path(tempfile.gettempdir())
            assert get_logo_data_uri(profile) is None

    def test_get_logo_data_uri_valid_file(self):
        profile = MagicMock(spec=BusinessProfile)
        profile.logo_path = "test_logo.png"

        with tempfile.TemporaryDirectory() as tmpdir:
            logo_dir = Path(tmpdir)
            logo_file = logo_dir / "test_logo.png"
            logo_file.write_bytes(b"PNG fake image data")

            with patch("invoice_machine.pdf.generator.settings") as mock_settings:
                mock_settings.logo_dir = logo_dir
                result = get_logo_data_uri(profile)

                assert result is not None
                # A complete data: URI, with the payload still valid base64.
                assert result.startswith("data:")
                import base64

                decoded = base64.b64decode(result.split(",", 1)[1])
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
        # Payment state, as every real invoice has.
        invoice.amount_paid = Decimal("0.00")
        invoice.amount_due = Decimal("1000.00")
        invoice.payment_link_url = None
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
    async def test_generate_pdf_creates_file(self, mock_invoice, mock_business_profile, db_session):
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

                        assert result == "pdfs/20250115-1-1.pdf"
                        assert (pdf_dir / "20250115-1-1.pdf").exists()

    @pytest.mark.asyncio
    async def test_generate_pdf_with_items(self, mock_invoice, mock_business_profile, db_session):
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

                        assert result == "pdfs/20250115-1-1.pdf"
                        pdf_file = pdf_dir / "20250115-1-1.pdf"
                        assert pdf_file.exists()
                        assert pdf_file.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_generate_pdf_with_tax(self, mock_invoice, mock_business_profile, db_session):
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

                        assert result == "pdfs/20250115-1-1.pdf"

    @pytest.mark.asyncio
    async def test_generate_pdf_quote(self, mock_invoice, mock_business_profile, db_session):
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

                        assert result == "pdfs/Q-20250115-1-1.pdf"

    @pytest.mark.asyncio
    async def test_generate_pdf_with_payment_methods(
        self, mock_invoice, mock_business_profile, db_session
    ):
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

                        assert result == "pdfs/20250115-1-1.pdf"

    @pytest.mark.asyncio
    async def test_generate_pdf_long_invoice_number(
        self, mock_invoice, mock_business_profile, db_session
    ):
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

                        assert "INV-20250115-SPECIAL-CLIENT-12345-1.pdf" in result


class TestPDFTemplate:
    """Tests for PDF template rendering."""

    def test_template_exists(self):
        template_path = Path(__file__).parent.parent / "invoice_machine" / "pdf" / "template.html"
        assert template_path.exists(), "PDF template file should exist"

    def test_template_has_required_elements(self):
        template_path = Path(__file__).parent.parent / "invoice_machine" / "pdf" / "template.html"
        content = template_path.read_text()

        assert "{{ invoice.invoice_number }}" in content or "invoice_number" in content
        assert "{{ business.name }}" in content or "business.name" in content
        assert "format_money" in content


class TestStoreInvoicePDF:
    """Regression tests for PDF freshness bookkeeping and filename uniqueness."""

    @pytest.mark.asyncio
    async def test_stamping_does_not_leave_invoice_permanently_stale(
        self, db_session, invoice_with_client, business_profile
    ):
        """A stamped PDF must not immediately look stale again.

        `updated_at` has an `onupdate` default that fires at flush time, always
        after the `pdf_generated_at` written in the same statement.
        """
        from invoice_machine.pdf.generator import store_invoice_pdf

        renders = []

        async def fake_generate(session, invoice):
            renders.append(invoice.id)
            return "pdfs/fake.pdf"

        with patch("invoice_machine.pdf.generator.generate_pdf", side_effect=fake_generate):
            await store_invoice_pdf(db_session, invoice_with_client)
            assert renders == [invoice_with_client.id]

            # Second and third fetches must reuse the stored PDF.
            await store_invoice_pdf(db_session, invoice_with_client)
            await store_invoice_pdf(db_session, invoice_with_client)
            assert renders == [invoice_with_client.id]

            assert not invoice_with_client.needs_pdf_regeneration

    @pytest.mark.asyncio
    async def test_real_edit_still_invalidates_the_pdf(
        self, db_session, invoice_with_client, business_profile
    ):
        """Editing the invoice must still force a re-render."""
        from invoice_machine.pdf.generator import store_invoice_pdf

        renders = []

        async def fake_generate(session, invoice):
            renders.append(invoice.id)
            return "pdfs/fake.pdf"

        with patch("invoice_machine.pdf.generator.generate_pdf", side_effect=fake_generate):
            await store_invoice_pdf(db_session, invoice_with_client)

            invoice_with_client.notes = "edited"
            await db_session.commit()
            await db_session.refresh(invoice_with_client)

            await store_invoice_pdf(db_session, invoice_with_client)

        assert len(renders) == 2

    @pytest.mark.asyncio
    async def test_force_always_rerenders(self, db_session, invoice_with_client, business_profile):
        """The explicit regenerate action bypasses the freshness check."""
        from invoice_machine.pdf.generator import store_invoice_pdf

        renders = []

        async def fake_generate(session, invoice):
            renders.append(invoice.id)
            return "pdfs/fake.pdf"

        with patch("invoice_machine.pdf.generator.generate_pdf", side_effect=fake_generate):
            await store_invoice_pdf(db_session, invoice_with_client)
            await store_invoice_pdf(db_session, invoice_with_client, force=True)

        assert len(renders) == 2

    def test_filenames_are_unique_across_punctuation_variants(self):
        """ "INV.001" and "INV001" must not share a PDF file.

        sanitize_filename_component drops dots, so the filename cannot be built
        from the invoice number alone.
        """
        from invoice_machine.pdf.generator import invoice_pdf_filename

        first = Invoice(id=1, invoice_number="INV.001", issue_date=date(2026, 1, 15))
        second = Invoice(id=2, invoice_number="INV001", issue_date=date(2026, 1, 15))

        assert invoice_pdf_filename(first) != invoice_pdf_filename(second)


class TestLogoDataUri:
    """The data: URI must describe the logo's real format, not always PNG."""

    def _profile_with_logo(self, logo_dir: Path, name: str, content: bytes) -> BusinessProfile:
        (logo_dir / name).write_bytes(content)
        profile = BusinessProfile(id=1, name="Test")
        profile.logo_path = name
        return profile

    def test_jpeg_logo_is_not_labelled_png(self):
        from invoice_machine.pdf.generator import get_logo_data_uri

        with tempfile.TemporaryDirectory() as tmpdir:
            logo_dir = Path(tmpdir)
            profile = self._profile_with_logo(
                logo_dir, "logo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 32
            )
            with patch("invoice_machine.pdf.generator.settings") as mock_settings:
                mock_settings.logo_dir = logo_dir
                assert get_logo_data_uri(profile).startswith("data:image/jpeg;base64,")

    def test_png_logo_is_labelled_png(self):
        from invoice_machine.pdf.generator import get_logo_data_uri

        with tempfile.TemporaryDirectory() as tmpdir:
            logo_dir = Path(tmpdir)
            profile = self._profile_with_logo(
                logo_dir, "logo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
            )
            with patch("invoice_machine.pdf.generator.settings") as mock_settings:
                mock_settings.logo_dir = logo_dir
                assert get_logo_data_uri(profile).startswith("data:image/png;base64,")

    def test_webp_logo_is_labelled_webp(self):
        from invoice_machine.pdf.generator import get_logo_data_uri

        with tempfile.TemporaryDirectory() as tmpdir:
            logo_dir = Path(tmpdir)
            profile = self._profile_with_logo(
                logo_dir, "logo.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 16
            )
            with patch("invoice_machine.pdf.generator.settings") as mock_settings:
                mock_settings.logo_dir = logo_dir
                assert get_logo_data_uri(profile).startswith("data:image/webp;base64,")
