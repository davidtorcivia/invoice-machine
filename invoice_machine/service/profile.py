"""Business profile update validation shared by the REST API and MCP tools."""

import json
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from invoice_machine.crypto import encrypt_credential
from invoice_machine.database import BusinessProfile
from invoice_machine.email import require_password_for_new_smtp_destination


class BusinessProfileUpdate(BaseModel):
    """Business profile update schema."""

    name: str | None = Field(None, max_length=255)
    business_name: str | None = Field(None, max_length=255)
    address_line1: str | None = Field(None, max_length=500)
    address_line2: str | None = Field(None, max_length=500)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    country: str | None = Field(None, max_length=100)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    ein: str | None = Field(None, max_length=50)
    # Interpolated into the PDF stylesheet, so nothing but a hex color may pass.
    accent_color: str | None = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    default_payment_terms_days: int | None = Field(None, ge=0, le=365)
    default_currency_code: str | None = Field(None, pattern="^[A-Z]{3}$")
    default_notes: str | None = Field(None, max_length=10000)
    default_payment_instructions: str | None = Field(None, max_length=10000)
    payment_methods: str | None = Field(None, max_length=10000)  # JSON string
    theme_preference: str | None = Field(None, pattern="^(system|light|dark)$")
    app_base_url: str | None = Field(None, max_length=500)
    # Bounded Decimal, not a free-form string: the rate reaches a DECIMAL column
    # and is applied to every subsequently created invoice.
    default_tax_enabled: bool | None = None
    default_tax_rate: Decimal | None = Field(None, ge=0, le=100)
    default_tax_name: str | None = Field(None, max_length=50)

    @field_validator("payment_methods")
    @classmethod
    def validate_payment_methods(cls, value: str | None) -> str | None:
        """Reject payment_methods that isn't a JSON array of {id, name, instructions}.

        Readers silently degrade unparseable JSON to an empty list, so an invalid
        value here would make a user's payment methods disappear.
        """
        if value is None or value == "":
            return value
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("payment_methods must be valid JSON") from None
        if not isinstance(parsed, list):
            raise ValueError("payment_methods must be a JSON array")
        if len(parsed) > 50:
            raise ValueError("payment_methods supports at most 50 entries")
        for entry in parsed:
            if not isinstance(entry, dict):
                raise ValueError("each payment method must be a JSON object")
            if not str(entry.get("id") or "").strip():
                raise ValueError("each payment method needs a non-empty id")
            if not str(entry.get("name") or "").strip():
                raise ValueError("each payment method needs a non-empty name")
        return value


class SMTPSettingsUpdate(BaseModel):
    """SMTP settings update request."""

    smtp_enabled: bool | None = None
    smtp_host: str | None = Field(None, max_length=255)
    smtp_port: int | None = Field(None, ge=1, le=65535)
    smtp_username: str | None = Field(None, max_length=255)
    smtp_password: str | None = Field(None, max_length=255)
    smtp_from_email: str | None = Field(None, max_length=255)
    smtp_from_name: str | None = Field(None, max_length=255)
    smtp_use_tls: bool | None = None


class EmailTemplatesUpdate(BaseModel):
    """Update email templates request."""

    email_subject_template: str | None = Field(None, max_length=500)
    email_body_template: str | None = Field(None, max_length=10000)


# Optional profile columns that an explicit `null` may legitimately clear. Every
# other column is NOT NULL (or has app-level meaning for its default), so a null
# there is treated as "leave unchanged".
NULLABLE_PROFILE_FIELDS = frozenset(
    {
        "business_name",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "postal_code",
        "email",
        "phone",
        "ein",
        "default_notes",
        "default_payment_instructions",
        "payment_methods",
        "app_base_url",
        "smtp_host",
        "smtp_username",
        "smtp_password",
        "smtp_from_email",
        "smtp_from_name",
    }
)


def apply_profile_updates(profile: BusinessProfile, updates: dict) -> None:
    """Write already-validated updates onto the profile.

    Raises ValueError when the stored SMTP password would be sent somewhere new.
    """
    require_password_for_new_smtp_destination(profile, updates)
    for key, value in updates.items():
        if value is None and key not in NULLABLE_PROFILE_FIELDS:
            continue
        if isinstance(value, bool):
            value = int(value)  # SQLite stores flags as integers
        elif key == "smtp_password" and value:
            value = encrypt_credential(value)
        setattr(profile, key, value)
