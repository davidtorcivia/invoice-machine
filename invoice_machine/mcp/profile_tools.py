"""Business profile MCP tools."""

from __future__ import annotations

from invoice_machine.database import BusinessProfile
from invoice_machine.presenters import dump_json_list, serialize_business_profile
from invoice_machine.service.profile import (
    BusinessProfileUpdate,
    EmailTemplatesUpdate,
    SMTPSettingsUpdate,
    apply_profile_updates,
)
from invoice_machine.utils import utc_now

from .annotations import ADDITIVE, DESTRUCTIVE, READ_ONLY, UPDATE
from .context import get_session, mcp

# REST validates each of these request bodies; MCP arguments go through the same models.
_UPDATE_MODELS = (BusinessProfileUpdate, SMTPSettingsUpdate, EmailTemplatesUpdate)


@mcp.tool(annotations=READ_ONLY)
async def get_business_profile() -> dict:
    """Retrieve the current business profile."""
    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)
        return serialize_business_profile(
            profile,
            json_ready=True,
            payment_methods_as_list=True,
        )


@mcp.tool(annotations=UPDATE)
async def update_business_profile(
    name: str | None = None,
    business_name: str | None = None,
    address_line1: str | None = None,
    address_line2: str | None = None,
    city: str | None = None,
    state: str | None = None,
    postal_code: str | None = None,
    country: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    ein: str | None = None,
    accent_color: str | None = None,
    default_payment_terms_days: int | None = None,
    default_notes: str | None = None,
    default_payment_instructions: str | None = None,
    theme_preference: str | None = None,
    default_tax_enabled: bool | None = None,
    default_tax_rate: float | None = None,
    default_tax_name: str | None = None,
    smtp_enabled: bool | None = None,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
    smtp_username: str | None = None,
    smtp_password: str | None = None,
    smtp_from_email: str | None = None,
    smtp_from_name: str | None = None,
    smtp_use_tls: bool | None = None,
    email_subject_template: str | None = None,
    email_body_template: str | None = None,
) -> dict:
    """
    Update business profile fields. Only provide the fields you want to change.

    Args:
        ein: Tax ID / EIN
        accent_color: PDF accent color (hex format, e.g. #0891b2)
        default_payment_terms_days: Default payment terms (e.g. 30 for Net 30)
        theme_preference: UI theme preference (system, light, dark)
        default_tax_rate: Default tax rate percentage (e.g. 8.25 for 8.25%)
        default_tax_name: Default tax name (e.g. "VAT", "Sales Tax", "GST")
        smtp_port: SMTP server port (default 587)
        smtp_use_tls: Use TLS/STARTTLS (default True)
        email_subject_template: Default email subject template with placeholders
        email_body_template: Default email body template with placeholders
    """

    # Copied before any other local exists so it holds only the tool arguments;
    # on Python <=3.12 locals() is the live frame dict, so it must be copied.
    arguments = dict(locals())

    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        # Validate inside the session: get_session turns a ValidationError (a
        # ValueError) into a ToolError the client can read.
        updates: dict = {}
        for model in _UPDATE_MODELS:
            fields = {
                k: v for k, v in arguments.items() if v is not None and k in model.model_fields
            }
            updates |= model.model_validate(fields).model_dump(exclude_unset=True)
        apply_profile_updates(profile, updates)

        profile.updated_at = utc_now()
        await session.commit()
        await session.refresh(profile)

        return serialize_business_profile(
            profile,
            json_ready=True,
            payment_methods_as_list=True,
        )


@mcp.tool(annotations=ADDITIVE)
async def add_payment_method(
    name: str,
    instructions: str,
) -> dict:
    """
    Add a new payment method to the business profile.

    Payment methods can be selected individually per invoice to show
    specific payment options on the PDF.

    Args:
        name: Payment method name (e.g., "Bank Transfer (ACH)", "Venmo", "Zelle")
        instructions: Payment details (e.g., bank account info, username, etc.)
    """
    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        new_method = {
            "id": str(int(utc_now().timestamp() * 1000)),
            "name": name,
            "instructions": instructions,
        }
        payment_methods = profile.payment_methods_list
        payment_methods.append(new_method)

        profile.payment_methods = dump_json_list(payment_methods)
        profile.updated_at = utc_now()
        await session.commit()

        return new_method


@mcp.tool(annotations=DESTRUCTIVE)
async def remove_payment_method(method_id: str) -> bool:
    """Remove a payment method from the business profile."""
    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        payment_methods = profile.payment_methods_list
        original_count = len(payment_methods)
        payment_methods = [m for m in payment_methods if m.get("id") != method_id]

        if len(payment_methods) == original_count:
            return False

        profile.payment_methods = dump_json_list(payment_methods)
        profile.updated_at = utc_now()
        await session.commit()

        return True
