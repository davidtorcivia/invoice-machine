"""Email service for sending invoices via SMTP."""

import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from typing import Optional

from starlette.concurrency import run_in_threadpool

from invoice_machine.database import Invoice, BusinessProfile
from invoice_machine.services import format_currency
from invoice_machine.utils import sanitize_filename_component
from invoice_machine.config import get_settings
from invoice_machine.crypto import decrypt_credential

settings = get_settings()


# Email validation regex (RFC 5322 simplified)
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)


def _sanitize_email(email: str) -> str:
    """
    Validate and sanitize email address to prevent header injection.

    Args:
        email: Email address to validate

    Returns:
        Sanitized email address

    Raises:
        ValueError: If email is invalid or contains injection attempts
    """
    if not email:
        raise ValueError("Email address is required")

    # Remove any whitespace
    email = email.strip()

    # Check for header injection attempts (newlines, carriage returns)
    if "\n" in email or "\r" in email:
        raise ValueError("Invalid email address: contains newline characters")

    # Validate email format
    if not EMAIL_REGEX.match(email):
        raise ValueError(f"Invalid email address format: {email}")

    return email


def _sanitize_header(value: str, field_name: str = "Header") -> str:
    """
    Sanitize header value to prevent header injection.

    Args:
        value: Header value to sanitize
        field_name: Name of the field for error messages

    Returns:
        Sanitized header value

    Raises:
        ValueError: If value contains injection attempts
    """
    if not value:
        return ""

    # Check for header injection attempts
    if "\n" in value or "\r" in value:
        raise ValueError(f"Invalid {field_name}: contains newline characters")

    # Remove any control characters
    sanitized = "".join(c for c in value if ord(c) >= 32 or c == "\t")

    return sanitized


# Default email templates
DEFAULT_SUBJECT_TEMPLATE = "{document_type} {invoice_number}"
DEFAULT_BODY_TEMPLATE = """Dear {client_name},

Please find attached {document_type_lower} {invoice_number} for {line_items}.

Amount: {total}
Due Date: {due_date}

Thank you for your business!

Best regards,
{your_name}"""


def expand_template(template: str, invoice: "Invoice", profile: "BusinessProfile") -> str:
    """
    Expand template placeholders with invoice and profile data.

    Supported placeholders:
    - {invoice_number}, {quote_number} - Document number
    - {document_type} - "Invoice" or "Quote"
    - {document_type_lower} - "invoice" or "quote"
    - {client_name} - Client contact name
    - {client_business_name} - Client business name
    - {client_email} - Client email
    - {total}, {amount} - Formatted total amount
    - {subtotal} - Formatted subtotal
    - {due_date} - Formatted due date
    - {issue_date} - Formatted issue date
    - {your_name} - Business profile name
    - {business_name} - Business name from profile
    - {line_items} - Comma-separated list of line item descriptions

    Args:
        template: Template string with placeholders
        invoice: Invoice object with data
        profile: BusinessProfile object with data

    Returns:
        Template with placeholders replaced by actual values
    """
    doc_type = "Quote" if getattr(invoice, "document_type", "invoice") == "quote" else "Invoice"
    total_formatted = format_currency(invoice.total, invoice.currency_code)
    subtotal_formatted = format_currency(invoice.subtotal, invoice.currency_code)
    due_date_str = invoice.due_date.strftime("%B %d, %Y") if invoice.due_date else "Upon receipt"
    issue_date_str = invoice.issue_date.strftime("%B %d, %Y") if invoice.issue_date else ""

    # Format line items as comma-separated descriptions
    # Handle cases where items relationship isn't loaded (lazy load may fail in async)
    try:
        items = invoice.items or []
        if items:
            line_items_text = ", ".join(item.description for item in items)
        else:
            line_items_text = "services rendered"
    except Exception:
        line_items_text = "services rendered"

    replacements = {
        "{invoice_number}": invoice.invoice_number,
        "{quote_number}": invoice.invoice_number,
        "{document_type}": doc_type,
        "{document_type_lower}": doc_type.lower(),
        "{client_name}": invoice.client_name or "Client",
        "{client_business_name}": invoice.client_business or invoice.client_name or "Client",
        "{client_email}": invoice.client_email or "",
        "{total}": total_formatted,
        "{amount}": total_formatted,
        "{subtotal}": subtotal_formatted,
        "{due_date}": due_date_str,
        "{issue_date}": issue_date_str,
        "{your_name}": profile.name or profile.business_name or "Invoice Machine",
        "{business_name}": profile.business_name or profile.name or "",
        "{line_items}": line_items_text,
    }

    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    return result


class EmailService:
    """Service for sending invoice emails via SMTP."""

    def __init__(self, profile: BusinessProfile):
        """
        Initialize with business profile containing SMTP settings.

        Args:
            profile: BusinessProfile with SMTP configuration
        """
        self.profile = profile

    def _get_smtp_password(self) -> Optional[str]:
        """Get decrypted SMTP password."""
        if not self.profile.smtp_password:
            return None
        try:
            return decrypt_credential(self.profile.smtp_password)
        except ValueError:
            # If decryption fails, try using as-is (for legacy unencrypted values)
            return self.profile.smtp_password

    def _validate_config(self) -> None:
        """Validate SMTP configuration is complete."""
        if not self.profile.smtp_enabled:
            raise ValueError("SMTP is not enabled. Configure SMTP settings first.")

        if not self.profile.smtp_host:
            raise ValueError("SMTP host is not configured.")

        if not self.profile.smtp_from_email:
            raise ValueError("SMTP from email is not configured.")

    def _send_email_sync(
        self,
        to_email: str,
        subject: str,
        body: str,
        attachment_path: Optional[Path] = None,
        attachment_filename: Optional[str] = None,
    ) -> bool:
        """
        Synchronous email sending (runs in thread pool).

        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Email body text
            attachment_path: Path to file to attach (optional)
            attachment_filename: Filename for attachment (optional)

        Returns:
            True if email sent successfully
        """
        self._validate_config()

        # Sanitize inputs to prevent header injection
        to_email = _sanitize_email(to_email)
        subject = _sanitize_header(subject, "Subject")

        # Create message
        msg = MIMEMultipart()
        from_name = _sanitize_header(self.profile.smtp_from_name or "", "From name")
        from_email = _sanitize_email(self.profile.smtp_from_email)
        msg["From"] = (
            f"{from_name} <{from_email}>"
            if from_name
            else from_email
        )
        msg["To"] = to_email
        msg["Subject"] = subject

        # Add body
        msg.attach(MIMEText(body, "plain"))

        # Add attachment if provided
        if attachment_path and attachment_path.exists():
            with open(attachment_path, "rb") as f:
                part = MIMEBase("application", "pdf")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                filename = attachment_filename or attachment_path.name
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{filename}"',
                )
                msg.attach(part)

        # Connect and send
        use_tls = bool(self.profile.smtp_use_tls)
        port = self.profile.smtp_port or 587

        # Decrypt password for authentication
        smtp_password = self._get_smtp_password()

        if use_tls and port == 465:
            # SSL connection (port 465)
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                self.profile.smtp_host, port, context=context
            ) as server:
                if self.profile.smtp_username and smtp_password:
                    server.login(self.profile.smtp_username, smtp_password)
                server.send_message(msg)
        else:
            # STARTTLS connection (port 587 or other)
            with smtplib.SMTP(self.profile.smtp_host, port) as server:
                if use_tls:
                    server.starttls()
                if self.profile.smtp_username and smtp_password:
                    server.login(self.profile.smtp_username, smtp_password)
                server.send_message(msg)

        return True

    async def send_invoice(
        self,
        invoice: Invoice,
        recipient_email: Optional[str] = None,
        subject: Optional[str] = None,
        body: Optional[str] = None,
    ) -> dict:
        """
        Send invoice PDF via email.

        Args:
            invoice: Invoice to send
            recipient_email: Override recipient (defaults to client email)
            subject: Override subject (defaults to "Invoice {number}")
            body: Override body (defaults to friendly message with details)

        Returns:
            Dict with success status and details
        """
        # Determine recipient
        to_email = recipient_email or invoice.client_email
        if not to_email:
            return {
                "success": False,
                "error": "No recipient email. Provide recipient_email or set client email.",
            }

        # Determine subject - use explicit override, profile template, or default
        if subject:
            email_subject = subject
        else:
            subject_template = self.profile.email_subject_template or DEFAULT_SUBJECT_TEMPLATE
            email_subject = expand_template(subject_template, invoice, self.profile)

        # Determine body - use explicit override, profile template, or default
        if body:
            email_body = body
        else:
            body_template = self.profile.email_body_template or DEFAULT_BODY_TEMPLATE
            email_body = expand_template(body_template, invoice, self.profile)

        # Get PDF path
        if not invoice.pdf_path:
            return {
                "success": False,
                "error": "Invoice PDF not generated. Generate PDF first.",
            }

        pdf_path = settings.data_dir / invoice.pdf_path
        if not pdf_path.exists():
            return {
                "success": False,
                "error": f"Invoice PDF not found at {invoice.pdf_path}",
            }

        # Send email in thread pool
        try:
            safe_invoice_number = sanitize_filename_component(
                invoice.invoice_number, f"invoice-{invoice.id}"
            )
            await run_in_threadpool(
                self._send_email_sync,
                to_email,
                email_subject,
                email_body,
                pdf_path,
                f"{safe_invoice_number}.pdf",
            )
            return {
                "success": True,
                "recipient": to_email,
                "subject": email_subject,
                "invoice_number": invoice.invoice_number,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    async def test_connection(self) -> dict:
        """
        Test SMTP connection without sending an email.

        Returns:
            Dict with success status and details
        """
        try:
            self._validate_config()

            # Decrypt password outside of nested function to use self
            smtp_password = self._get_smtp_password()

            def _test_sync():
                use_tls = bool(self.profile.smtp_use_tls)
                port = self.profile.smtp_port or 587

                if use_tls and port == 465:
                    context = ssl.create_default_context()
                    with smtplib.SMTP_SSL(
                        self.profile.smtp_host, port, context=context
                    ) as server:
                        if self.profile.smtp_username and smtp_password:
                            server.login(
                                self.profile.smtp_username, smtp_password
                            )
                else:
                    with smtplib.SMTP(self.profile.smtp_host, port) as server:
                        if use_tls:
                            server.starttls()
                        if self.profile.smtp_username and smtp_password:
                            server.login(
                                self.profile.smtp_username, smtp_password
                            )

            await run_in_threadpool(_test_sync)
            return {
                "success": True,
                "message": f"Successfully connected to {self.profile.smtp_host}:{self.profile.smtp_port}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
