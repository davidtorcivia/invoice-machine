"""Settings for online payments (Stripe) and automated payment reminders."""

import json
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.crypto import encrypt_credential
from invoice_machine.database import BusinessProfile, get_session
from invoice_machine.rate_limit import limiter
from invoice_machine.service.reminders import (
    DEFAULT_REMINDER_BODY,
    DEFAULT_REMINDER_OFFSETS,
    DEFAULT_REMINDER_SUBJECT,
    validate_reminder_offsets,
    validate_timezone,
)
from invoice_machine.utils import utc_now

logger = logging.getLogger(__name__)
router = APIRouter(tags=["payment-settings"])


class PaymentSettingsSchema(BaseModel):
    """Online payment settings. Secrets are never returned, only their presence."""

    payments_enabled: bool
    payments_provider: str | None = None
    stripe_secret_key_set: bool = False
    stripe_webhook_secret_set: bool = False
    webhook_url: str | None = None


class PaymentSettingsUpdate(BaseModel):
    """Update online payment settings."""

    payments_enabled: bool | None = None
    payments_provider: str | None = Field(None, pattern="^(stripe)$")
    # Write-only. Send an empty string to clear.
    stripe_secret_key: str | None = Field(None, max_length=300)
    stripe_webhook_secret: str | None = Field(None, max_length=300)

    @field_validator("stripe_secret_key")
    @classmethod
    def validate_secret_key(cls, value: str | None) -> str | None:
        """Reject anything that isn't a Stripe secret/restricted key."""
        if not value:
            return value
        key = value.strip()
        if not key.startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_")):
            raise ValueError(
                "Expected a Stripe secret key (sk_...) or restricted key (rk_...). "
                "A restricted key limited to Checkout Sessions is strongly preferred."
            )
        return key

    @field_validator("stripe_webhook_secret")
    @classmethod
    def validate_webhook_secret(cls, value: str | None) -> str | None:
        if not value:
            return value
        secret = value.strip()
        if not secret.startswith("whsec_"):
            raise ValueError("Expected a Stripe webhook signing secret (whsec_...)")
        return secret


class ReminderSettingsSchema(BaseModel):
    """Automated payment reminder settings."""

    reminders_enabled: bool
    reminder_offsets: list[int]
    reminder_subject_template: str | None = None
    reminder_body_template: str | None = None
    business_timezone: str = "UTC"
    reminder_send_hour: int = 9
    local_time: str | None = None
    default_offsets: list[int] = list(DEFAULT_REMINDER_OFFSETS)
    default_subject: str = DEFAULT_REMINDER_SUBJECT
    default_body: str = DEFAULT_REMINDER_BODY
    smtp_enabled: bool = False


class ReminderSettingsUpdate(BaseModel):
    """Update automated payment reminder settings."""

    reminders_enabled: bool | None = None
    # Day offsets relative to the due date; negative = before due.
    reminder_offsets: list[int] | None = Field(None, max_length=10)
    reminder_subject_template: str | None = Field(None, max_length=500)
    reminder_body_template: str | None = Field(None, max_length=10000)
    # IANA name, e.g. "America/New_York". Governs both when reminders send and
    # how "days until due" is counted.
    business_timezone: str | None = Field(None, max_length=64)
    reminder_send_hour: int | None = Field(None, ge=0, le=23)


class FxRatesSchema(BaseModel):
    """Default exchange rates into the business base currency."""

    base_currency_code: str
    rates: dict[str, str]


class FxRatesUpdate(BaseModel):
    """Replace the stored exchange-rate table."""

    rates: dict[str, Decimal] = Field(default_factory=dict)

    @field_validator("rates")
    @classmethod
    def validate_rates(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        if len(value) > 50:
            raise ValueError("At most 50 exchange rates are supported")
        for code, rate in value.items():
            if len(code) != 3 or not code.isalpha():
                raise ValueError(f"'{code}' is not a 3-letter currency code")
            if not rate.is_finite() or rate <= 0:
                raise ValueError(f"Rate for {code} must be a positive number")
        return value


def _payment_settings_response(profile: BusinessProfile) -> dict:
    from invoice_machine.config import get_settings

    base_url = (profile.app_base_url or get_settings().app_base_url or "").rstrip("/")
    return {
        "payments_enabled": bool(profile.payments_enabled),
        "payments_provider": profile.payments_provider,
        # Presence only — the values themselves are write-only.
        "stripe_secret_key_set": bool(profile.stripe_secret_key),
        "stripe_webhook_secret_set": bool(profile.stripe_webhook_secret),
        "webhook_url": f"{base_url}/api/webhooks/stripe" if base_url else None,
    }


@router.get("/api/settings/payments", response_model=PaymentSettingsSchema)
@limiter.limit("60/minute")
async def get_payment_settings(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get online payment settings (secrets are never returned)."""
    profile = await BusinessProfile.get_or_create(session)
    return _payment_settings_response(profile)


@router.put("/api/settings/payments", response_model=PaymentSettingsSchema)
@limiter.limit("20/hour")
async def update_payment_settings(
    request: Request,
    data: PaymentSettingsUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update online payment settings. Credentials are encrypted before storage."""
    profile = await BusinessProfile.get_or_create(session)
    updates = data.model_dump(exclude_unset=True)

    if "payments_enabled" in updates and updates["payments_enabled"] is not None:
        profile.payments_enabled = int(updates["payments_enabled"])
    if "payments_provider" in updates and updates["payments_provider"]:
        profile.payments_provider = updates["payments_provider"]

    for field in ("stripe_secret_key", "stripe_webhook_secret"):
        if field not in updates:
            continue
        value = updates[field]
        # An empty string clears the credential; a value is encrypted at rest.
        setattr(profile, field, encrypt_credential(value) if value else None)

    # Refuse to advertise payments as on when they cannot possibly work: without
    # a key no link can be created, and without a signing secret no payment can
    # ever be recorded back.
    if profile.payments_enabled and not profile.stripe_secret_key:
        raise HTTPException(
            status_code=400,
            detail="Add a Stripe API key before enabling online payments.",
        )
    if not profile.payments_provider:
        profile.payments_provider = "stripe"

    profile.updated_at = utc_now()
    await session.commit()
    await session.refresh(profile)
    return _payment_settings_response(profile)


@router.post("/api/settings/payments/test")
@limiter.limit("10/minute")
async def test_payment_credentials(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Verify the stored Stripe credentials with a trivial authenticated call."""
    from invoice_machine.service.stripe_links import verify_stripe_key

    profile = await BusinessProfile.get_or_create(session)
    result = await verify_stripe_key(profile)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Verification failed"))

    if not profile.stripe_webhook_secret:
        result["warning"] = (
            "No webhook signing secret is configured, so completed payments will "
            "not be recorded automatically."
        )
    return result


@router.get("/api/settings/reminders", response_model=ReminderSettingsSchema)
@limiter.limit("60/minute")
async def get_reminder_settings(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get automated payment reminder settings."""
    from invoice_machine.service.reminders import business_now

    profile = await BusinessProfile.get_or_create(session)
    return {
        "reminders_enabled": bool(profile.reminders_enabled),
        "reminder_offsets": profile.reminder_offsets_list or list(DEFAULT_REMINDER_OFFSETS),
        "reminder_subject_template": profile.reminder_subject_template,
        "reminder_body_template": profile.reminder_body_template,
        "business_timezone": profile.business_timezone or "UTC",
        "reminder_send_hour": (
            profile.reminder_send_hour if profile.reminder_send_hour is not None else 9
        ),
        # Shown in the UI so the configured timezone can be sanity-checked at a glance.
        "local_time": business_now(profile).strftime("%Y-%m-%d %H:%M"),
        "smtp_enabled": bool(profile.smtp_enabled),
    }


@router.put("/api/settings/reminders", response_model=ReminderSettingsSchema)
@limiter.limit("30/hour")
async def update_reminder_settings(
    request: Request,
    data: ReminderSettingsUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update automated payment reminder settings."""
    profile = await BusinessProfile.get_or_create(session)
    updates = data.model_dump(exclude_unset=True)

    if updates.get("reminder_offsets") is not None:
        try:
            offsets = validate_reminder_offsets(updates["reminder_offsets"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        profile.reminder_offsets = json.dumps(offsets)

    if updates.get("reminders_enabled") is not None:
        profile.reminders_enabled = int(updates["reminders_enabled"])

    if updates.get("business_timezone") is not None:
        try:
            profile.business_timezone = validate_timezone(updates["business_timezone"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    if updates.get("reminder_send_hour") is not None:
        profile.reminder_send_hour = int(updates["reminder_send_hour"])

    for field in ("reminder_subject_template", "reminder_body_template"):
        if field in updates:
            # Empty string resets to the built-in default.
            setattr(profile, field, updates[field] or None)

    if profile.reminders_enabled and not profile.smtp_enabled:
        raise HTTPException(
            status_code=400,
            detail="Configure SMTP before enabling reminders — there is no way to send them.",
        )

    profile.updated_at = utc_now()
    await session.commit()
    await session.refresh(profile)

    return await get_reminder_settings(request, session)


@router.post("/api/settings/reminders/run")
@limiter.limit("5/hour")
async def run_reminders_now(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Run the reminder sweep immediately (same dedup rules as the daily job)."""
    from invoice_machine.service.reminders import send_due_reminders

    results = await send_due_reminders(session)
    return {
        "attempted": len(results),
        "sent": sum(1 for result in results if result.get("success")),
        "results": results,
    }


@router.get("/api/settings/fx-rates", response_model=FxRatesSchema)
@limiter.limit("60/minute")
async def get_fx_rates(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get the default exchange rates used when issuing foreign-currency invoices."""
    profile = await BusinessProfile.get_or_create(session)
    return {
        "base_currency_code": profile.default_currency_code or "USD",
        "rates": {code: str(rate) for code, rate in profile.fx_rates_map.items()},
    }


@router.put("/api/settings/fx-rates", response_model=FxRatesSchema)
@limiter.limit("30/hour")
async def update_fx_rates(
    request: Request,
    data: FxRatesUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Replace the exchange-rate table.

    Rates apply to invoices created from now on; existing invoices keep the rate
    captured when they were issued.
    """
    profile = await BusinessProfile.get_or_create(session)
    base = (profile.default_currency_code or "USD").upper()

    rates = {code.upper(): str(rate) for code, rate in data.rates.items()}
    # The base currency is always 1 by definition; storing it invites drift.
    rates.pop(base, None)

    profile.fx_rates = json.dumps(rates) if rates else None
    profile.updated_at = utc_now()
    await session.commit()
    await session.refresh(profile)

    return {
        "base_currency_code": base,
        "rates": {code: str(rate) for code, rate in profile.fx_rates_map.items()},
    }
