"""Security tests for path traversal, input validation, and IDOR protection."""

from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import Invoice, InvoiceItem, BusinessProfile
from invoice_machine.services import (
    BackupService,
    InvoiceService,
    ClientService,
)
from invoice_machine.email import _sanitize_email, _sanitize_header
from invoice_machine.api.profile import validate_image_content


class TestPathTraversalProtection:
    """Tests for path traversal prevention in BackupService."""

    def test_backup_filename_rejects_path_separators(self, temp_db_path):
        """Path separators are rejected in backup filenames."""
        service = BackupService(backup_dir=Path(temp_db_path).parent)

        with pytest.raises(ValueError, match="path separators not allowed"):
            service._validate_backup_filename("../etc/passwd")

        with pytest.raises(ValueError, match="path separators not allowed"):
            service._validate_backup_filename("..\\windows\\system32\\config")

        with pytest.raises(ValueError, match="path separators not allowed"):
            service._validate_backup_filename("subdir/backup.db")

    def test_backup_filename_rejects_parent_directory_refs(self, temp_db_path):
        """Parent directory references are rejected."""
        service = BackupService(backup_dir=Path(temp_db_path).parent)

        with pytest.raises(ValueError, match="parent directory reference not allowed"):
            service._validate_backup_filename("..backup.db")

    def test_backup_filename_accepts_valid_names(self, temp_db_path):
        """Valid backup filenames are accepted."""
        service = BackupService(backup_dir=Path(temp_db_path).parent)

        # These should not raise
        path = service._validate_backup_filename("invoice_machine_backup_20250115_120000.db")
        assert path.name == "invoice_machine_backup_20250115_120000.db"

        path = service._validate_backup_filename("backup.db.gz")
        assert path.name == "backup.db.gz"

    def test_restore_backup_validates_filename(self, temp_db_path):
        """restore_backup validates filename before processing."""
        service = BackupService(backup_dir=Path(temp_db_path).parent)

        with pytest.raises(ValueError, match="path separators not allowed"):
            service.restore_backup("../../../etc/passwd")

    def test_delete_backup_validates_filename(self, temp_db_path):
        """delete_backup validates filename before processing."""
        service = BackupService(backup_dir=Path(temp_db_path).parent)

        with pytest.raises(ValueError, match="path separators not allowed"):
            service.delete_backup("../../../etc/passwd")


class TestEmailHeaderInjection:
    """Tests for email header injection prevention."""

    def test_email_rejects_newlines(self):
        """Email addresses with newlines are rejected."""
        with pytest.raises(ValueError, match="contains newline characters"):
            _sanitize_email("user@example.com\nBcc: attacker@evil.com")

        with pytest.raises(ValueError, match="contains newline characters"):
            _sanitize_email("user@example.com\r\nBcc: attacker@evil.com")

    def test_email_rejects_invalid_format(self):
        """Invalid email formats are rejected."""
        with pytest.raises(ValueError, match="Invalid email address format"):
            _sanitize_email("not-an-email")

        with pytest.raises(ValueError, match="Invalid email address format"):
            _sanitize_email("user@")

        with pytest.raises(ValueError, match="Invalid email address format"):
            _sanitize_email("@example.com")

    def test_email_accepts_valid_addresses(self):
        """Valid email addresses are accepted."""
        assert _sanitize_email("user@example.com") == "user@example.com"
        assert _sanitize_email("user.name+tag@domain.co.uk") == "user.name+tag@domain.co.uk"
        assert _sanitize_email("  user@example.com  ") == "user@example.com"

    def test_header_rejects_newlines(self):
        """Headers with newlines are rejected."""
        with pytest.raises(ValueError, match="contains newline characters"):
            _sanitize_header("Subject\nBcc: attacker@evil.com", "Subject")

        with pytest.raises(ValueError, match="contains newline characters"):
            _sanitize_header("Name\r\nX-Injection: value", "From name")

    def test_header_accepts_valid_values(self):
        """Valid header values are accepted."""
        assert _sanitize_header("Invoice 12345", "Subject") == "Invoice 12345"
        assert _sanitize_header("John Doe", "From name") == "John Doe"
        assert _sanitize_header("", "Subject") == ""


class TestIDORProtection:
    """Tests for Insecure Direct Object Reference prevention."""

    @pytest.mark.asyncio
    async def test_update_item_validates_invoice_relationship(self, db_session, business_profile):
        """update_item validates that item belongs to specified invoice."""
        # Create two invoices
        invoice1 = await InvoiceService.create_invoice(db_session)
        invoice2 = await InvoiceService.create_invoice(db_session)

        # Add item to invoice1
        item = await InvoiceService.add_item(
            db_session, invoice1.id, description="Test", quantity=1, unit_price=100
        )

        # Try to update item claiming it belongs to invoice2 (IDOR attempt)
        with pytest.raises(ValueError, match="does not belong to the specified invoice"):
            await InvoiceService.update_item(
                db_session, item.id, invoice_id=invoice2.id, description="Hacked"
            )

    @pytest.mark.asyncio
    async def test_remove_item_validates_invoice_relationship(self, db_session, business_profile):
        """remove_item validates that item belongs to specified invoice."""
        # Create two invoices
        invoice1 = await InvoiceService.create_invoice(db_session)
        invoice2 = await InvoiceService.create_invoice(db_session)

        # Add item to invoice1
        item = await InvoiceService.add_item(
            db_session, invoice1.id, description="Test", quantity=1, unit_price=100
        )

        # Try to delete item claiming it belongs to invoice2 (IDOR attempt)
        with pytest.raises(ValueError, match="does not belong to the specified invoice"):
            await InvoiceService.remove_item(db_session, item.id, invoice_id=invoice2.id)


class TestInputValidation:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_add_item_rejects_negative_quantity(self, db_session, business_profile):
        """add_item rejects negative quantity."""
        invoice = await InvoiceService.create_invoice(db_session)

        with pytest.raises(ValueError, match="Quantity cannot be negative"):
            await InvoiceService.add_item(
                db_session, invoice.id, description="Test", quantity=-1, unit_price=100
            )

    @pytest.mark.asyncio
    async def test_add_item_rejects_negative_price(self, db_session, business_profile):
        """add_item rejects negative unit price."""
        invoice = await InvoiceService.create_invoice(db_session)

        with pytest.raises(ValueError, match="Unit price cannot be negative"):
            await InvoiceService.add_item(
                db_session, invoice.id, description="Test", quantity=1, unit_price=-50
            )

    @pytest.mark.asyncio
    async def test_add_item_rejects_invalid_unit_type(self, db_session, business_profile):
        """add_item rejects invalid unit type."""
        invoice = await InvoiceService.create_invoice(db_session)

        with pytest.raises(ValueError, match="Invalid unit type"):
            await InvoiceService.add_item(
                db_session, invoice.id, description="Test", quantity=1, unit_price=100, unit_type="invalid"
            )

    @pytest.mark.asyncio
    async def test_update_item_rejects_negative_quantity(self, db_session, business_profile):
        """update_item rejects negative quantity."""
        invoice = await InvoiceService.create_invoice(db_session)
        item = await InvoiceService.add_item(
            db_session, invoice.id, description="Test", quantity=1, unit_price=100
        )

        with pytest.raises(ValueError, match="Quantity cannot be negative"):
            await InvoiceService.update_item(db_session, item.id, quantity=-1)

    @pytest.mark.asyncio
    async def test_update_item_rejects_negative_price(self, db_session, business_profile):
        """update_item rejects negative unit price."""
        invoice = await InvoiceService.create_invoice(db_session)
        item = await InvoiceService.add_item(
            db_session, invoice.id, description="Test", quantity=1, unit_price=100
        )

        with pytest.raises(ValueError, match="Unit price cannot be negative"):
            await InvoiceService.update_item(db_session, item.id, unit_price=-50)

    @pytest.mark.asyncio
    async def test_update_invoice_rejects_invalid_status(self, db_session, business_profile):
        """update_invoice rejects invalid status values."""
        invoice = await InvoiceService.create_invoice(db_session)

        with pytest.raises(ValueError, match="Invalid status"):
            await InvoiceService.update_invoice(db_session, invoice.id, status="invalid_status")

    @pytest.mark.asyncio
    async def test_update_invoice_accepts_valid_status(self, db_session, business_profile):
        """update_invoice accepts valid status values."""
        invoice = await InvoiceService.create_invoice(db_session)

        for status in ["draft", "sent", "paid", "overdue", "cancelled"]:
            updated = await InvoiceService.update_invoice(db_session, invoice.id, status=status)
            assert updated.status == status


class TestTaxRateValidation:
    """Tests for tax rate validation."""

    @pytest.mark.asyncio
    async def test_create_invoice_rejects_tax_rate_over_100(self, db_session, business_profile):
        """Tax rate over 100% is rejected."""
        with pytest.raises(ValueError, match="Tax rate must be between 0 and 100"):
            await InvoiceService.create_invoice(
                db_session,
                tax_enabled=True,
                tax_rate=Decimal("150.00"),
            )

    @pytest.mark.asyncio
    async def test_create_invoice_rejects_negative_tax_rate(self, db_session, business_profile):
        """Negative tax rate is rejected."""
        with pytest.raises(ValueError, match="Tax rate must be between 0 and 100"):
            await InvoiceService.create_invoice(
                db_session,
                tax_enabled=True,
                tax_rate=Decimal("-5.00"),
            )

    @pytest.mark.asyncio
    async def test_create_invoice_accepts_valid_tax_rate(self, db_session, business_profile):
        """Valid tax rates are accepted."""
        invoice = await InvoiceService.create_invoice(
            db_session,
            tax_enabled=True,
            tax_rate=Decimal("8.25"),
            items=[{"description": "Test", "quantity": 1, "unit_price": 100}],
        )
        assert invoice.tax_rate == Decimal("8.25")


class TestFileUploadSecurity:
    """Tests for file upload security."""

    def test_validates_png_signature(self):
        """PNG magic bytes are recognized."""
        png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        assert validate_image_content(png_header) is True

    def test_validates_jpeg_signature(self):
        """JPEG magic bytes are recognized."""
        jpeg_header = b"\xff\xd8\xff" + b"\x00" * 100
        assert validate_image_content(jpeg_header) is True

    def test_validates_gif_signature(self):
        """GIF magic bytes are recognized."""
        gif87a = b"GIF87a" + b"\x00" * 100
        gif89a = b"GIF89a" + b"\x00" * 100
        assert validate_image_content(gif87a) is True
        assert validate_image_content(gif89a) is True

    def test_validates_webp_signature(self):
        """WebP magic bytes are recognized."""
        webp = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 100
        assert validate_image_content(webp) is True

    def test_rejects_svg_for_security(self):
        """SVG is rejected due to XSS security risks (can contain embedded JavaScript)."""
        svg1 = b"<svg" + b" " * 100
        svg2 = b"<?xml" + b" " * 100
        assert validate_image_content(svg1) is False
        assert validate_image_content(svg2) is False

    def test_rejects_non_image_content(self):
        """Non-image content is rejected."""
        # Plain text
        assert validate_image_content(b"Hello, World!") is False
        # JavaScript
        assert validate_image_content(b"alert('xss');") is False
        # HTML
        assert validate_image_content(b"<!DOCTYPE html>") is False
        # PDF
        assert validate_image_content(b"%PDF-1.4") is False
        # EXE
        assert validate_image_content(b"MZ\x90\x00") is False

    def test_rejects_empty_content(self):
        """Empty content is rejected."""
        assert validate_image_content(b"") is False
        assert validate_image_content(b"\x00\x00") is False

    def test_rejects_short_content(self):
        """Content shorter than minimum signature is rejected."""
        assert validate_image_content(b"PNG") is False
        assert validate_image_content(b"\xff\xd8") is False
