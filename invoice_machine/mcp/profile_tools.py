"""Business profile MCP tools."""

from __future__ import annotations

import re
from decimal import Decimal

from invoice_machine.database import BusinessProfile
from invoice_machine.presenters import dump_json_list, serialize_business_profile
from invoice_machine.utils import utc_now

from .annotations import ADDITIVE, DESTRUCTIVE, READ_ONLY, UPDATE
from .context import get_session, mcp


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

    async with get_session() as session:
        profile = await BusinessProfile.get_or_create(session)

        updates = {
            k: v
            for k, v in locals().items()
            if v is not None and k not in ("session", "json", "Decimal", "re")
        }

        # accent_color is interpolated into the PDF stylesheet; enforce the same
        # strict hex pattern the REST endpoint uses so a crafted value can't break
        # out of the CSS context (the MCP path is otherwise unvalidated).
        if "accent_color" in updates and not re.fullmatch(
            r"#[0-9a-fA-F]{6}", updates["accent_color"]
        ):
            raise ValueError("accent_color must be a hex color like #0891b2")

        if "theme_preference" in updates and updates["theme_preference"] not in (
            "system",
            "light",
            "dark",
        ):
            raise ValueError("theme_preference must be one of: system, light, dark")

        if "smtp_password" in updates:
            from invoice_machine.crypto import encrypt_credential

            if updates["smtp_password"]:
                updates["smtp_password"] = encrypt_credential(updates["smtp_password"])
            else:
                updates["smtp_password"] = None

        if "default_tax_enabled" in updates:
            updates["default_tax_enabled"] = 1 if updates["default_tax_enabled"] else 0
        if "default_tax_rate" in updates:
            # Bounded like the REST schema: an out-of-range rate here would be
            # applied to every subsequently created invoice.
            rate = Decimal(str(updates["default_tax_rate"]))
            if not rate.is_finite() or rate < 0 or rate > 100:
                raise ValueError("default_tax_rate must be between 0 and 100")
            updates["default_tax_rate"] = rate

        if "smtp_enabled" in updates:
            updates["smtp_enabled"] = 1 if updates["smtp_enabled"] else 0
        if "smtp_use_tls" in updates:
            updates["smtp_use_tls"] = 1 if updates["smtp_use_tls"] else 0

        for key, value in updates.items():
            setattr(profile, key, value)

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
