"""Email service for sending invoices via SMTP."""

import re
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from invoice_machine.config import get_settings
from invoice_machine.crypto import UnencryptedCredentialError, decrypt_credential
from invoice_machine.database import BusinessProfile, Invoice
from invoice_machine.services import format_currency
from invoice_machine.utils import confined_file, refuse_disallowed_host, sanitize_filename_component

settings = get_settings()


EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _validate_smtp_target(host: str, port: int) -> None:
    refuse_disallowed_host(host, port, kind="SMTP host")


def _sanitize_email(email: str) -> str:
    """Validate an address and reject anything that could inject a header."""
    if not email:
        raise ValueError("Email address is required")

    email = email.strip()

    if "\n" in email or "\r" in email:
        raise ValueError("Invalid email address: contains newline characters")

    if not EMAIL_REGEX.match(email):
        raise ValueError(f"Invalid email address format: {email}")

    return email


def _sanitize_header(value: str, field_name: str = "Header") -> str:
    """Strip control characters from a header value and reject newlines."""
    if not value:
        return ""

    if "\n" in value or "\r" in value:
        raise ValueError(f"Invalid {field_name}: contains newline characters")

    sanitized = "".join(c for c in value if ord(c) >= 32 or c == "\t")

    return sanitized


DEFAULT_SUBJECT_TEMPLATE = "{document_type} {invoice_number}"
DEFAULT_BODY_TEMPLATE = """Dear {client_name},

Please find attached {document_type_lower} {invoice_number} for {line_items}.

Amount: {total}
Due Date: {due_date}

Thank you for your business!

Best regards,
{your_name}"""


def expand_template(template: str, invoice: "Invoice", profile: "BusinessProfile") -> str:
    """Expand template placeholders with invoice and profile data."""
    doc_type = "Quote" if getattr(invoice, "document_type", "invoice") == "quote" else "Invoice"
    total_formatted = format_currency(invoice.total, invoice.currency_code)
    subtotal_formatted = format_currency(invoice.subtotal, invoice.currency_code)
    due_date_str = invoice.due_date.strftime("%B %d, %Y") if invoice.due_date else "Upon receipt"
    issue_date_str = invoice.issue_date.strftime("%B %d, %Y") if invoice.issue_date else ""

    # The items relationship may not be loaded; a lazy load can fail under async.
    try:
        items = invoice.items or []
        if items:
            line_items_text = ", ".join(item.description for item in items)
        else:
            line_items_text = "services rendered"
    except Exception:
        line_items_text = "services rendered"

    amount_due_formatted = format_currency(invoice.amount_due, invoice.currency_code)
    amount_paid_formatted = format_currency(invoice.amount_paid or 0, invoice.currency_code)
    # A quote is not a bill, so never surface a pay-now link on one.
    payment_link = (
        invoice.payment_link_url or ""
        if getattr(invoice, "document_type", "invoice") != "quote"
        else ""
    )

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
        "{amount_paid}": amount_paid_formatted,
        "{amount_due}": amount_due_formatted,
        "{payment_link}": payment_link,
        "{due_date}": due_date_str,
        "{issue_date}": issue_date_str,
        "{your_name}": profile.name or profile.business_name or "Invoice Machine",
        "{business_name}": profile.business_name or profile.name or "",
        "{line_items}": line_items_text,
    }

    # Single pass over the source template: a value that happens to contain a
    # placeholder (e.g. a client literally named "{total}") must not then be
    # expanded itself.
    result: list[str] = []
    index = 0
    while index < len(template):
        for placeholder, value in replacements.items():
            if template.startswith(placeholder, index):
                result.append(value)
                index += len(placeholder)
                break
        else:
            result.append(template[index])
            index += 1
    return "".join(result)


class EmailService:
    """Service for sending invoice emails via SMTP."""

    def __init__(self, profile: BusinessProfile):
        self.profile = profile

    def _get_smtp_password(self) -> str | None:
        """Decrypt the stored SMTP password, or None if none is set."""
        if not self.profile.smtp_password:
            return None
        try:
            return decrypt_credential(self.profile.smtp_password)
        except UnencryptedCredentialError:
            raise
        except ValueError as exc:
            raise ValueError(
                "Stored SMTP password could not be decrypted. Re-save it in settings."
            ) from exc

    def _validate_config(self) -> tuple[str, str]:
        """Validate SMTP configuration and return the checked (host, from_email)."""
        if not self.profile.smtp_enabled:
            raise ValueError("SMTP is not enabled. Configure SMTP settings first.")

        if not self.profile.smtp_host:
            raise ValueError("SMTP host is not configured.")

        if not self.profile.smtp_from_email:
            raise ValueError("SMTP from email is not configured.")

        return self.profile.smtp_host, self.profile.smtp_from_email

    def _send_email_sync(
        self,
        to_email: str,
        subject: str,
        body: str,
        attachment_path: Path | None = None,
        attachment_filename: str | None = None,
    ) -> bool:
        """Send one message synchronously; call it off the event loop."""
        host, profile_from_email = self._validate_config()

        to_email = _sanitize_email(to_email)
        subject = _sanitize_header(subject, "Subject")

        msg = MIMEMultipart()
        from_name = _sanitize_header(self.profile.smtp_from_name or "", "From name")
        from_email = _sanitize_email(profile_from_email)
        # formataddr quotes/escapes the display name: an unescaped name containing
        # <> or a comma can forge extra addresses.
        msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

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

        use_tls = bool(self.profile.smtp_use_tls)
        port = self.profile.smtp_port or 587

        # SSRF guard before any outbound connection.
        _validate_smtp_target(host, port)

        smtp_password = self._get_smtp_password()

        if use_tls and port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context) as server:
                if self.profile.smtp_username and smtp_password:
                    server.login(self.profile.smtp_username, smtp_password)
                server.send_message(msg)
        else:
            # STARTTLS (port 587 or other). Pass a verifying context: the
            # smtplib default is CERT_NONE, which accepts any certificate.
            with smtplib.SMTP(host, port) as server:
                if use_tls:
                    server.starttls(context=ssl.create_default_context())
                if self.profile.smtp_username and smtp_password:
                    server.login(self.profile.smtp_username, smtp_password)
                server.send_message(msg)

        return True

    async def send_invoice(
        self,
        invoice: Invoice,
        recipient_email: str | None = None,
        subject: str | None = None,
        body: str | None = None,
    ) -> dict:
        """Send the invoice PDF by email, returning a success/error dict."""
        to_email = recipient_email or invoice.client_email
        if not to_email:
            return {
                "success": False,
                "error": "No recipient email. Provide recipient_email or set client email.",
            }

        if subject:
            email_subject = subject
        else:
            subject_template = self.profile.email_subject_template or DEFAULT_SUBJECT_TEMPLATE
            email_subject = expand_template(subject_template, invoice, self.profile)

        if body:
            email_body = body
        else:
            body_template = self.profile.email_body_template or DEFAULT_BODY_TEMPLATE
            email_body = expand_template(body_template, invoice, self.profile)

        if not invoice.pdf_path:
            return {
                "success": False,
                "error": "Invoice PDF not generated. Generate PDF first.",
            }

        pdf_path = confined_file(settings.pdf_dir, Path(invoice.pdf_path).name)
        if pdf_path is None or not pdf_path.is_file():
            return {
                "success": False,
                "error": "Invoice PDF not found.",
            }

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
        """Test the SMTP connection without sending an email."""
        try:
            host, _ = self._validate_config()

            smtp_password = self._get_smtp_password()

            def _test_sync():
                use_tls = bool(self.profile.smtp_use_tls)
                port = self.profile.smtp_port or 587

                # SSRF guard before any outbound connection.
                _validate_smtp_target(host, port)

                if use_tls and port == 465:
                    context = ssl.create_default_context()
                    with smtplib.SMTP_SSL(host, port, context=context) as server:
                        if self.profile.smtp_username and smtp_password:
                            server.login(self.profile.smtp_username, smtp_password)
                else:
                    with smtplib.SMTP(host, port) as server:
                        if use_tls:
                            server.starttls(context=ssl.create_default_context())
                        if self.profile.smtp_username and smtp_password:
                            server.login(self.profile.smtp_username, smtp_password)

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
