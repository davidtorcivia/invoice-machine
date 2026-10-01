"""Export everything as a Books Machine "invoice-machine-import" bundle.

Books Machine imports the bundle in one transaction and rejects it whole on the
first invalid record, so this module normalizes anything Invoice Machine can
hold but Books Machine refuses, and records each change as a warning the
importer shows before the user commits. The limits below mirror Books Machine's
import schema.

Rows are read with raw SQL rather than the ORM: SQLite does not enforce
DECIMAL scale, and the ORM would round a stored 8.875% tax rate to 8.88.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.config import get_settings
from invoice_machine.service.common import line_item_total, quantize_money
from invoice_machine.service.reminders import DEFAULT_REMINDER_OFFSETS
from invoice_machine.utils import INVOICE_NUMBER_PATTERN, confined_file, utc_now

FORMAT = "invoice-machine-import"
FORMAT_VERSION = 1

MAX_ITEMS = 100
MAX_SELECTED_METHODS = 20
MAX_PAYMENT = Decimal("99999999.99")
MAX_QUANTITY = Decimal("10000")
MAX_EXCHANGE_RATE = Decimal("1000000")
MAX_DECIMAL = Decimal("1e12")
MAX_DIGITS = 12  # integer digits below MAX_DECIMAL
MAX_LOGO_BYTES = 5 * 1024 * 1024
MAX_WARNINGS = 1000
MAX_WARNING_LENGTH = 1000
STATUSES = {"draft", "sent", "paid", "overdue", "cancelled"}
FREQUENCIES = {"daily", "weekly", "monthly", "quarterly", "yearly"}
MARKED_PAID = "system_mark_paid"

# zod 4's email pattern, which Books Machine applies to client and business emails.
_EMAIL = re.compile(
    r"(?!\.)(?!.*\.\.)([A-Za-z0-9_'+\-\.]*)[A-Za-z0-9_+-]@([A-Za-z0-9][A-Za-z0-9\-]*\.)+[A-Za-z]{2,}"
)
# Intl.supportedValuesOf("currency") in workerd, which Books Machine checks codes against.
# ponytail: a snapshot; regenerate if Books Machine rejects a code this list accepts.
SUPPORTED_CURRENCIES = frozenset(
    """
    AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD
    BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUC CUP CVE CZK DJF DKK DOP DZD EGP ERN
    ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HRK HTG HUF IDR ILS INR IQD
    IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD
    MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB
    PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLL SOS SRD
    SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VES VND
    VUV WST XAF XCD XDR XOF XPF XSU YER ZAR ZMW ZWL
    """.split()
)
_ACCENT = re.compile(r"#[0-9a-fA-F]{6}")
_DEFAULT_ACCENT = "#16a34a"
# The characters JavaScript's String.prototype.trim removes; Python's strip keeps U+FEFF.
_JS_WHITESPACE = (
    " \t\n\v\f\r\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008"
    "\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)


def _utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _fit(value: Any, limit: int, what: str, warnings: list[str]) -> str | None:
    """Trim text to a Books Machine length cap, measured in UTF-16 units as JavaScript does."""
    if value is None:
        return None
    result = str(value)
    if _utf16_length(result) <= limit:
        return result
    original = len(result)
    while _utf16_length(result) > limit:
        result = result[: -max(1, (_utf16_length(result) - limit) // 2)]
    warnings.append(f"{what} exceeded {limit} characters ({original}); the rest was cut.")
    return result


def _decimal(value: Any, *, round_tiny: bool = True) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(repr(value)) if isinstance(value, float) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    # Larger values cannot be money here and overflow JavaScript's safe integers there.
    # adjusted(), not abs(): abs() applies the context and overflows on 1E+1000000.
    if not result.is_finite() or (result and result.adjusted() >= MAX_DIGITS):
        return None
    # Digits past 12 places carry no money; unrounded they can exceed Books Machine's
    # 100-character decimal strings (a stored 1e-100 prints as 102 characters).
    exponent = result.as_tuple().exponent
    if round_tiny and isinstance(exponent, int) and exponent < -12:
        return result.quantize(Decimal("1e-12"))
    return result


def _plain(value: Decimal) -> str:
    return format(value.normalize(), "f") if value == value.to_integral() else format(value, "f")


def _date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10]).isoformat()
    except ValueError:
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None
    # Invoice Machine stores naive UTC.
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _timestamp(value: Any, fallback: str) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return fallback
    # Books Machine accepts only the Z form.
    return parsed.strftime("%Y-%m-%dT%H:%M:%S.") + f"{parsed.microsecond // 1000:03d}Z"


def _bool(value: Any, default: bool) -> bool:
    return default if value is None else bool(value)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _clamped(value: Any, bounds: tuple[int, int], what: str, warnings: list[str]) -> int:
    low, high = bounds
    try:
        exact: Decimal | None = Decimal(str(value).strip())
        number: int | None = int(exact)
    except (InvalidOperation, ValueError, OverflowError):
        exact, number = None, None
    result = low if number is None else min(max(number, low), high)
    if value is not None and exact != result:
        warnings.append(f"{what} was {str(value)[:20]!r}; {result} was used.")
    return result


def _trimmed(value: Any) -> str | None:
    """Text as JavaScript's trim() leaves it, or None when nothing is left."""
    return (str(value).strip(_JS_WHITESPACE) or None) if value is not None else None


def _json(value: Any) -> Any:
    if value is None or value == "":
        return None
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return None


def _email(value: Any, what: str, warnings: list[str]) -> str | None:
    if value is None or not str(value).strip():
        return None
    candidate = str(value).strip()
    if _EMAIL.fullmatch(candidate) and len(candidate) <= 255:
        return candidate
    warnings.append(f"{what} {candidate[:255]!r} is not a single valid address; it was left blank.")
    return None


def _currency(value: Any, fallback: str | None, what: str, warnings: list[str]) -> str | None:
    if value is None or not str(value).strip():
        return fallback
    code = str(value).strip().upper()
    if code in SUPPORTED_CURRENCIES:
        return code
    warnings.append(
        f"{what} has unrecognized currency {str(value)[:20]!r}; {fallback or 'none'} was used."
    )
    return fallback


def _terms(value: Any, default: int, what: str, warnings: list[str]) -> int:
    days = _int(value, default)
    clamped = min(max(days, 0), 365)
    if clamped != days:
        warnings.append(f"{what} had payment terms of {days} days; {clamped} was used.")
    return clamped


def _tax_rate(value: Any, what: str, warnings: list[str]) -> str | None:
    rate = _decimal(value)
    if value is not None and rate is None:
        warnings.append(
            f"{what} has an unreadable tax rate {str(value)[:20]!r}; it was left unset."
        )
    if rate is None:
        return None
    clamped = min(max(rate, Decimal(0)), Decimal(100))
    if clamped != rate:
        warnings.append(f"{what} had a tax rate of {rate}%; {clamped}% was used.")
    return _plain(clamped)


def _exchange_rate(value: Any, what: str, warnings: list[str]) -> str | None:
    rate = _decimal(value)
    if rate is None:
        if value is not None:
            warnings.append(f"{what} has an unreadable exchange rate; it was left unset.")
        return None
    if not Decimal(0) < rate <= MAX_EXCHANGE_RATE:
        warnings.append(
            f"{what} has exchange rate {rate}, outside 0 to 1000000; it was left unset."
        )
        return None
    return _plain(rate)


def _selected_methods(value: Any, what: str, warnings: list[str]) -> list[str] | None:
    parsed = _json(value)
    if value is not None and value != "" and not isinstance(parsed, list):
        warnings.append(f"{what} has unreadable selected payment methods; none were kept.")
        return None
    if not isinstance(parsed, list):
        return None
    methods = [
        _fit(method, 100, f"{what} selected payment method", warnings) or ""
        for method in parsed
        if isinstance(method, (str, int)) and not isinstance(method, bool)
    ]
    if len(methods) != len(parsed):
        warnings.append(f"{what} has unreadable selected payment methods; those were left out.")
    if len(methods) > MAX_SELECTED_METHODS:
        warnings.append(
            f"{what} selected {len(methods)} payment methods; the first {MAX_SELECTED_METHODS} were kept."
        )
    return methods[:MAX_SELECTED_METHODS]


def _items(
    rows: list[dict[str, Any]], what: str, warnings: list[str], stored_totals: bool
) -> list[dict[str, Any]]:
    """Map line items, folding any Books Machine cannot hold into lines with the same total."""
    items: list[dict[str, Any]] = []
    for row in rows:
        price = _decimal(row.get("unit_price"))
        # Unrounded, so a quantity off the 3-decimal grid is folded with a warning.
        quantity = _decimal(row.get("quantity"), round_tiny=False)
        unit_type = row.get("unit_type") or "qty"
        description = str(row.get("description") or "")
        if unit_type not in ("qty", "hours"):
            warnings.append(
                f"{what} has a line with unit type {str(unit_type)[:20]!r}; it was imported as qty."
            )
            unit_type = "qty"
        if price is None or price < 0:
            warnings.append(
                f"{what} has a line {description[:60]!r} with an unusable price; it was left out."
            )
            continue
        if quantity is None:
            if row.get("quantity") is not None:
                warnings.append(
                    f"{what} has a line {description[:60]!r} with an unusable quantity; it was left out."
                )
                continue
            quantity = Decimal(1)
        if (
            quantity <= 0
            or quantity > MAX_QUANTITY
            or quantity != quantity.quantize(Decimal("0.001"))
        ):
            total = _decimal(row.get("total")) if stored_totals else None
            total = quantize_money(total if total is not None else line_item_total(price, quantity))
            if total < 0:
                warnings.append(
                    f"{what} has a line {description[:60]!r} with a negative total; it was left out."
                )
                continue
            warnings.append(
                f"{what} has a line {description[:60]!r} with quantity {quantity}; "
                f"it was imported as one unit of {total} so the total is unchanged."
            )
            description = f"{description} ({quantity} x {price})"
            price, quantity, unit_type = total, Decimal(1), "qty"
        items.append(
            {
                "description": description,
                "quantity": _plain(quantity.quantize(Decimal("0.001"))),
                "unitType": unit_type,
                "unitPrice": _plain(price),
            }
        )
    if len(items) > MAX_ITEMS:
        rest = items[MAX_ITEMS - 1 :]
        subtotal = sum(
            (line_item_total(item["unitPrice"], item["quantity"]) for item in rest), Decimal(0)
        )
        warnings.append(
            f"{what} has {len(items)} lines; the last {len(rest)} were combined into one line of {subtotal}."
        )
        items = items[: MAX_ITEMS - 1] + [
            {
                "description": f"Combined {len(rest)} further lines",
                "quantity": "1",
                "unitType": "qty",
                "unitPrice": str(subtotal),
            }
        ]
    kept = []
    for item in items:
        if line_item_total(item["unitPrice"], item["quantity"]) >= MAX_DECIMAL:
            warnings.append(
                f"{what} has a line {item['description'][:60]!r} too large to import; it was left out."
            )
        else:
            kept.append(item)
    items = kept
    for index, item in enumerate(items):
        item["description"] = (
            _fit(item["description"], 2000, f"{what} line {index + 1}", warnings) or ""
        )
        item["sortOrder"] = index
    return items


def _bounded_total(
    items: list[dict[str, Any]], tax_rate: str, what: str, warnings: list[str]
) -> list[dict[str, Any]]:
    """Leave the lines out when the taxed total would overflow Books Machine's integer cents."""
    subtotal = sum((line_item_total(i["unitPrice"], i["quantity"]) for i in items), Decimal(0))
    if subtotal * (1 + Decimal(tax_rate) / 100) < MAX_DECIMAL:
        return items
    warnings.append(
        f"{what} totals {subtotal} before tax, too large to import; its lines were left out."
    )
    return []


async def _rows(session: AsyncSession, query: str) -> list[dict[str, Any]]:
    return [dict(row) for row in (await session.execute(text(query))).mappings().all()]


def _valid_number(number: str) -> bool:
    return bool(INVOICE_NUMBER_PATTERN.fullmatch(number)) and ".." not in number


def _invoice_number(
    raw: Any, row_id: int, taken: set[str], reserved: set[str], warnings: list[str]
) -> str:
    """Keep every valid number; rename the rest without colliding with any kept or earlier number."""
    original = str(raw or "").strip()
    number = original
    if not _valid_number(number):
        number = re.sub(r"[^A-Za-z0-9._-]+", "-", number)
        number = re.sub(r"\.{2,}", ".", number).lstrip("._-")[:50] or f"IM-{row_id}"
    if number in taken or (number in reserved and number != str(raw)):
        base, attempt = number, 0
        while number in taken or number in reserved:
            attempt += 1
            suffix = f"-{row_id}" if attempt == 1 else f"-{row_id}-{attempt}"
            number = base[: 50 - len(suffix)] + suffix
        warnings.append(
            f"Invoice number {original[:60]!r} duplicates another invoice there; it was imported as {number}."
        )
    elif number != original:
        warnings.append(
            f"Invoice number {original[:60]!r} is not valid in Books Machine; it was imported as {number}."
        )
    taken.add(number)
    return number


def _logo(filename: Any, warnings: list[str]) -> dict[str, str] | None:
    if not filename:
        return None
    name = str(filename).rsplit("/", 1)[-1]
    path = confined_file(get_settings().logo_dir, name)
    data = None
    if path is not None and path.is_file() and path.stat().st_size <= MAX_LOGO_BYTES:
        data = path.read_bytes()
    kinds = (
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
    )
    mime = next((kind for magic, kind in kinds if data and data.startswith(magic)), None)
    if data and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        mime = "image/webp"
    if not data or not mime:
        warnings.append(
            f"The logo {name[:100]!r} could not be read; upload it again in Books Machine."
        )
        return None
    return {
        "filename": name[:255],
        "mimeType": mime,
        "dataBase64": base64.b64encode(data).decode("ascii"),
    }


def _profile(profile: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    currency = (
        _currency(profile.get("default_currency_code"), "USD", "The business profile", warnings)
        or "USD"
    )

    rates: dict[str, str] = {}
    raw_rates = _json(profile.get("fx_rates"))
    if profile.get("fx_rates") and not isinstance(raw_rates, dict):
        warnings.append("The saved exchange rates could not be read; none were exported.")
    for code, value in (raw_rates or {}).items() if isinstance(raw_rates, dict) else ():
        rate = _decimal(value)
        upper = str(code).strip().upper()
        if (
            upper in SUPPORTED_CURRENCIES
            and rate is not None
            and Decimal(0) < rate <= MAX_EXCHANGE_RATE
        ):
            rates[upper] = _plain(rate)
        else:
            warnings.append(
                f"Exchange rate {str(code)[:16]} = {str(value)[:32]} is invalid and was not exported."
            )

    offsets = _json(profile.get("reminder_offsets"))
    if not isinstance(offsets, list):
        if profile.get("reminder_offsets"):
            warnings.append("The reminder schedule could not be read; the default was used.")
        offsets = list(DEFAULT_REMINDER_OFFSETS)
    clean_offsets = sorted(
        {
            int(o)
            for o in offsets
            if isinstance(o, (int, float)) and not isinstance(o, bool) and -365 <= o <= 365
        }
    )
    if len(clean_offsets) > 10 or len(clean_offsets) != len(offsets):
        warnings.append(
            "Some reminder days were out of range or duplicated; only valid ones were kept."
        )
        clean_offsets = clean_offsets[:10]

    methods = _json(profile.get("payment_methods"))
    if profile.get("payment_methods") and not isinstance(methods, list):
        warnings.append("The saved payment methods could not be read; none were exported.")
    methods = methods if isinstance(methods, list) else None
    while methods and _utf16_length(json.dumps(methods)) > 10_000:
        dropped = methods.pop()
        name = dropped.get("name") if isinstance(dropped, dict) else dropped
        warnings.append(
            f"Payment method {str(name)[:60]!r} did not fit the size limit and was not exported."
        )

    accent = str(profile.get("accent_color") or "")
    timezone = str(profile.get("business_timezone") or "UTC").strip() or "UTC"
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        warnings.append(f"Time zone {timezone[:64]!r} is unknown; UTC was used.")
        timezone = "UTC"

    def fit(column: str, limit: int, label: str) -> str | None:
        return _fit(profile.get(column), limit, f"Business {label}", warnings)

    if profile.get("smtp_enabled"):
        warnings.append(
            "Email (SMTP) settings and passwords are not exported; set up email in Books Machine."
        )
    if profile.get("payments_enabled"):
        warnings.append(
            "Online payment (Stripe) keys are not exported; connect Stripe again in Books Machine."
        )

    return {
        "name": fit("name", 255, "contact name") or "",
        "businessName": fit("business_name", 255, "name"),
        "businessAddressLine1": fit("address_line1", 500, "address line 1"),
        "businessAddressLine2": fit("address_line2", 500, "address line 2"),
        "businessCity": fit("city", 100, "city"),
        "businessState": fit("state", 100, "state"),
        "businessPostalCode": fit("postal_code", 20, "postal code"),
        "businessCountry": fit("country", 100, "country"),
        "businessTaxId": fit("ein", 50, "tax ID"),
        "businessEmail": _email(profile.get("email"), "The business email", warnings),
        "businessPhone": fit("phone", 50, "phone"),
        "timezone": timezone,
        "currency": currency,
        "fxRates": json.dumps(rates),
        "accentColor": accent if _ACCENT.fullmatch(accent) else _DEFAULT_ACCENT,
        "defaultPaymentTermsDays": _terms(
            profile.get("default_payment_terms_days"), 30, "The business profile", warnings
        ),
        "taxEnabled": _bool(profile.get("default_tax_enabled"), False),
        "taxRate": _tax_rate(profile.get("default_tax_rate"), "The business profile", warnings)
        or "0",
        "taxName": fit("default_tax_name", 50, "tax name") or "Tax",
        "paymentInstructions": fit("default_payment_instructions", 10_000, "payment instructions"),
        "defaultNotes": fit("default_notes", 10_000, "default notes"),
        "paymentMethods": json.dumps(methods) if methods is not None else None,
        "emailSubjectTemplate": fit("email_subject_template", 500, "email subject"),
        "emailBodyTemplate": fit("email_body_template", 10_000, "email body"),
        "reminderSubjectTemplate": fit("reminder_subject_template", 500, "reminder subject"),
        "reminderBodyTemplate": fit("reminder_body_template", 10_000, "reminder body"),
        "reminderOffsets": json.dumps(clean_offsets, separators=(",", ":")),
        "remindersEnabled": _bool(profile.get("reminders_enabled"), False),
        "reminderSendHour": min(max(_int(profile.get("reminder_send_hour"), 9), 0), 23),
        "trashRetentionDays": min(max(get_settings().trash_retention_days, 1), 3650),
    }


def _client(row: dict[str, Any], now: str, warnings: list[str]) -> dict[str, Any]:
    what = (
        f"Client {row['id']} ({str(row.get('business_name') or row.get('name') or 'unnamed')[:60]})"
    )
    name = _trimmed(row.get("name"))
    business = _trimmed(row.get("business_name"))
    email = _email(row.get("email"), f"{what} email", warnings)
    if not name and not business:
        name = email or f"Client {row['id']}"
        warnings.append(f"{what} had no name; it was imported as {name!r}.")
    created = _timestamp(row.get("created_at"), now)
    return {
        "sourceId": str(row["id"]),
        "createdAt": created,
        "updatedAt": _timestamp(row.get("updated_at"), created),
        "deletedAt": _timestamp(row["deleted_at"], created) if row.get("deleted_at") else None,
        "data": {
            "name": _fit(name, 255, f"{what} name", warnings),
            "businessName": _fit(business, 255, f"{what} business name", warnings),
            "addressLine1": _fit(row.get("address_line1"), 500, f"{what} address line 1", warnings),
            "addressLine2": _fit(row.get("address_line2"), 500, f"{what} address line 2", warnings),
            "city": _fit(row.get("city"), 100, f"{what} city", warnings),
            "state": _fit(row.get("state"), 100, f"{what} state", warnings),
            "postalCode": _fit(row.get("postal_code"), 20, f"{what} postal code", warnings),
            "country": _fit(row.get("country"), 100, f"{what} country", warnings),
            "email": email,
            "phone": _fit(row.get("phone"), 50, f"{what} phone", warnings),
            "paymentTermsDays": _terms(row.get("payment_terms_days"), 30, what, warnings),
            "notes": _fit(row.get("notes"), 5000, f"{what} notes", warnings),
            "taxEnabled": None if row.get("tax_enabled") is None else bool(row["tax_enabled"]),
            "taxRate": _tax_rate(row.get("tax_rate"), what, warnings),
            "taxName": _fit(row.get("tax_name"), 50, f"{what} tax name", warnings),
            "preferredCurrency": _currency(row.get("preferred_currency"), None, what, warnings),
        },
    }


def _payment(
    row: dict[str, Any], created: str, what: str, warnings: list[str]
) -> dict[str, Any] | None:
    amount = _decimal(row.get("amount"))
    if amount is None or amount <= 0 or amount > MAX_PAYMENT:
        warnings.append(
            f"{what} has a payment of {row.get('amount')!r}, which cannot be imported; it was left out."
        )
        return None
    payment_date = _date(row.get("payment_date")) or created[:10]
    payment_created = _timestamp(row.get("created_at"), created)
    method = row.get("method")
    return {
        "sourceId": str(row["id"]),
        "createdAt": payment_created,
        "updatedAt": _timestamp(row.get("updated_at"), payment_created),
        "data": {
            "amount": str(quantize_money(amount)),
            "paymentDate": payment_date,
            "method": method
            if method == MARKED_PAID
            else _fit(method, 50, f"{what} payment method", warnings),
            "reference": _fit(row.get("reference"), 255, f"{what} payment reference", warnings),
            "notes": _fit(row.get("notes"), 2000, f"{what} payment notes", warnings),
            "provider": _fit(row.get("provider"), 100, f"{what} payment provider", warnings),
            "externalId": _fit(
                row.get("external_id"), 255, f"{what} payment external id", warnings
            ),
            "idempotencyKey": f"invoice-machine:{row['id']}",
            "allowOverpayment": True,
        },
    }


def _paid_date(value: Any, zone: ZoneInfo) -> str | None:
    parsed = _parse_timestamp(value)
    return parsed.astimezone(zone).date().isoformat() if parsed else None


def _reminders_sent(value: Any) -> list[int]:
    parsed = _json(value)
    if not isinstance(parsed, list):
        return []
    return sorted(
        {
            int(o)
            for o in parsed
            if isinstance(o, (int, float)) and not isinstance(o, bool) and -365 <= o <= 365
        }
    )[:100]


async def build_books_machine_bundle(session: AsyncSession) -> dict[str, Any]:
    """Collect every client, document, payment and schedule into one importable bundle."""
    now = _timestamp(utc_now(), "")
    warnings: list[str] = []

    profiles = await _rows(session, "SELECT * FROM business_profile ORDER BY id LIMIT 1")
    profile_row = profiles[0] if profiles else {}
    profile = _profile(profile_row, warnings)
    zone = ZoneInfo(profile["timezone"])

    client_rows = await _rows(session, "SELECT * FROM clients ORDER BY id")
    clients = [_client(row, now, warnings) for row in client_rows]
    client_ids = {client["sourceId"] for client in clients}

    invoice_rows = await _rows(session, "SELECT * FROM invoices ORDER BY id")
    item_rows = await _rows(
        session, "SELECT * FROM invoice_items ORDER BY invoice_id, sort_order, id"
    )
    payment_rows = await _rows(
        session, "SELECT * FROM payments ORDER BY invoice_id, payment_date, id"
    )
    items_by_invoice: dict[Any, list[dict[str, Any]]] = {}
    for item in item_rows:
        items_by_invoice.setdefault(item["invoice_id"], []).append(item)
    payments_by_invoice: dict[Any, list[dict[str, Any]]] = {}
    for payment in payment_rows:
        payments_by_invoice.setdefault(payment["invoice_id"], []).append(payment)

    by_id = {row["id"]: row for row in invoice_rows}
    taken: set[str] = set()
    reserved = {
        str(row["invoice_number"])
        for row in invoice_rows
        if _valid_number(str(row["invoice_number"] or ""))
    }
    used_targets: set[Any] = set()
    invoices = []
    for row in invoice_rows:
        number = _invoice_number(row.get("invoice_number"), row["id"], taken, reserved, warnings)
        what = f"Invoice {number}"
        created = _timestamp(row.get("created_at"), now)
        document_type = row.get("document_type") or "invoice"
        if document_type not in ("invoice", "quote"):
            warnings.append(
                f"{what} has document type {str(document_type)[:20]!r}; it was imported as an invoice."
            )
            document_type = "invoice"
        status = row.get("status")
        if status not in STATUSES:
            warnings.append(f"{what} has status {str(status)[:20]!r}; it was imported as a draft.")
            status = "draft"
        currency = (
            _currency(row.get("currency_code"), profile["currency"], what, warnings)
            or profile["currency"]
        )

        payments = [
            payment
            for source in payments_by_invoice.get(row["id"], [])
            if (payment := _payment(source, created, what, warnings)) is not None
        ]
        payment_total = sum((Decimal(p["data"]["amount"]) for p in payments), Decimal(0))
        if any(
            str(source.get("currency_code") or currency).upper() != currency
            for source in payments_by_invoice.get(row["id"], [])
        ):
            warnings.append(
                f"{what} has payments recorded in another currency; they were imported in {currency}."
            )
        exchange_rate = _exchange_rate(row.get("exchange_rate"), what, warnings)
        if (
            exchange_rate is not None
            and str(row.get("currency_code") or "").strip().upper() != currency
        ):
            warnings.append(f"{what} had a rate for its original currency; it was left unset.")
            exchange_rate = None
        if exchange_rate is None and currency != profile["currency"]:
            warnings.append(
                f"{what} in {currency} has no recorded exchange rate; Books Machine applies "
                f"its saved {currency} rate, if any, at import."
            )
        recorded = _decimal(row.get("amount_paid")) or Decimal(0)
        if quantize_money(recorded) != payment_total:
            warnings.append(
                f"{what} showed {quantize_money(recorded)} paid, but its payments add up to "
                f"{payment_total}; the payments were imported as recorded."
            )
        if document_type == "quote":
            if payments:
                amounts = ", ".join(p["data"]["amount"] for p in payments)
                warnings.append(
                    f"Quote {number} had payments ({amounts} {currency}), which Books Machine "
                    "only records on invoices; they were left out."
                )
                payments = []
            if status in ("paid", "overdue"):
                warnings.append(f"Quote {number} was marked {status}; it was imported as sent.")
                status = "sent"
        elif status == "cancelled" and payments:
            warnings.append(
                f"{what} is cancelled but has {payment_total} {currency} in payments. Books Machine "
                "cannot cancel an invoice with payments, so it was imported as issued; refund or credit it."
            )
            status = "sent"

        client_id = row.get("client_id")
        client_source = str(client_id) if client_id is not None else None
        if client_source is not None and client_source not in client_ids:
            warnings.append(
                f"{what} pointed at a client that no longer exists; it was imported without one."
            )
            client_source = None

        # Only links whose target survived; each target may be claimed once.
        converted_from = row.get("converted_from_invoice_id")
        if converted_from not in by_id:
            converted_from = None
        converted_to = row.get("converted_to_invoice_id")
        target = by_id.get(converted_to)
        if (
            target is None
            or target.get("converted_from_invoice_id") != row["id"]
            or converted_to in used_targets
        ):
            converted_to = None
        else:
            used_targets.add(converted_to)

        tax_rate = _tax_rate(row.get("tax_rate"), what, warnings) or "0"
        stored_total = _decimal(row.get("total"))
        if (
            status in ("sent", "overdue")
            and stored_total is not None
            and stored_total > 0
            and payment_total >= quantize_money(stored_total)
        ):
            warnings.append(
                f"{what} is marked {status} but its payments cover the total; it will import as paid."
            )
        invoice = {
            "sourceId": str(row["id"]),
            "clientSourceId": client_source,
            "status": status,
            "convertedFromSourceId": str(converted_from) if converted_from is not None else None,
            "convertedToSourceId": str(converted_to) if converted_to is not None else None,
            "createdAt": created,
            "updatedAt": _timestamp(row.get("updated_at"), created),
            "deletedAt": _timestamp(row["deleted_at"], created) if row.get("deleted_at") else None,
            "payments": payments,
            "clientSnapshot": {
                "name": _fit(row.get("client_name"), 255, f"{what} client name", warnings),
                "business": _fit(
                    row.get("client_business"), 255, f"{what} client business", warnings
                ),
                "email": _email(row.get("client_email"), f"{what} client email", warnings),
                "address": _fit(
                    row.get("client_address"), 2000, f"{what} client address", warnings
                ),
            },
            "paidAt": _paid_date(row.get("paid_at"), zone) if status == "paid" else None,
            "remindersSent": _reminders_sent(row.get("reminders_sent")),
            "lastReminderSentAt": (
                _timestamp(row["last_reminder_sent_at"], created)
                if row.get("last_reminder_sent_at")
                else None
            ),
            "expectedTotal": str(quantize_money(stored_total))
            if stored_total is not None
            else None,
            "data": {
                "issueDate": _date(row.get("issue_date")) or created[:10],
                "dueDate": _date(row.get("due_date")),
                "paymentTermsDays": _terms(row.get("payment_terms_days"), 30, what, warnings),
                "currencyCode": currency,
                "notes": _fit(row.get("notes"), 5000, f"{what} notes", warnings),
                "documentType": document_type,
                "invoiceNumberOverride": number,
                "clientReference": _fit(
                    row.get("client_reference"), 255, f"{what} client reference", warnings
                ),
                "showPaymentInstructions": _bool(row.get("show_payment_instructions"), True),
                "selectedPaymentMethods": _selected_methods(
                    row.get("selected_payment_methods"), what, warnings
                ),
                "taxEnabled": _bool(row.get("tax_enabled"), False),
                "taxRate": tax_rate,
                "taxName": _fit(row.get("tax_name"), 50, f"{what} tax name", warnings) or "Tax",
                "exchangeRate": exchange_rate,
                "items": _bounded_total(
                    _items(items_by_invoice.get(row["id"], []), what, warnings, stored_totals=True),
                    tax_rate if row.get("tax_enabled") else "0",
                    what,
                    warnings,
                ),
            },
        }
        if stored_total is None:
            # Optional but not nullable in Books Machine's schema.
            del invoice["expectedTotal"]
        invoices.append(invoice)

    schedules = []
    for row in await _rows(session, "SELECT * FROM recurring_schedules ORDER BY id"):
        name = _trimmed(row.get("name")) or f"Recurring schedule {row['id']}"
        what = f"Recurring schedule {name[:60]!r}"
        client_source = str(row.get("client_id"))
        if client_source not in client_ids:
            warnings.append(
                f"{what} pointed at a client that no longer exists; it was not exported."
            )
            continue
        frequency = row.get("frequency")
        if frequency not in FREQUENCIES:
            warnings.append(f"{what} has frequency {str(frequency)[:20]!r}; it was not exported.")
            continue
        created = _timestamp(row.get("created_at"), now)
        raw_items = _json(row.get("line_items"))
        if row.get("line_items") and not isinstance(raw_items, list):
            warnings.append(f"{what} has unreadable line items; it was exported without them.")
        line_items = (
            [item for item in raw_items or [] if isinstance(item, dict)]
            if isinstance(raw_items, list)
            else []
        )
        # An inherited tax setting is unknown here, so bound as if taxed at 100%.
        if row.get("tax_enabled") is None:
            bound_tax = "100"
        elif row["tax_enabled"]:
            # No readable rate means Books Machine inherits one, so assume the worst.
            bound_tax = _tax_rate(row.get("tax_rate"), what, []) or "100"
        else:
            bound_tax = "0"
        schedule_month = row.get("schedule_month")
        last_invoice = row.get("last_invoice_id")
        currency = (
            _currency(row.get("currency_code"), profile["currency"], what, warnings)
            or profile["currency"]
        )
        schedules.append(
            {
                "sourceId": str(row["id"]),
                "clientSourceId": client_source,
                "lastInvoiceSourceId": str(last_invoice) if last_invoice in by_id else None,
                "isActive": _bool(row.get("is_active"), True),
                "createdAt": created,
                "updatedAt": _timestamp(row.get("updated_at"), created),
                "deletedAt": None,
                "data": {
                    "name": _fit(name, 255, f"{what} name", warnings),
                    "frequency": frequency,
                    "scheduleDay": _clamped(
                        row.get("schedule_day"),
                        (0, 6)
                        if frequency == "weekly"
                        else (1, 31)
                        if frequency != "daily"
                        else (0, 31),
                        f"{what} schedule day",
                        warnings,
                    ),
                    "scheduleMonth": _clamped(schedule_month, (1, 12), f"{what} month", warnings)
                    if schedule_month is not None
                    else None,
                    "quarterMonth": _clamped(
                        row.get("quarter_month"), (1, 3), f"{what} quarter month", warnings
                    ),
                    "currencyCode": currency,
                    "paymentTermsDays": _terms(row.get("payment_terms_days"), 30, what, warnings),
                    "notes": _fit(row.get("notes"), 5000, f"{what} notes", warnings),
                    "useDefaultNotes": _bool(row.get("use_default_notes"), True),
                    "items": _bounded_total(
                        _items(line_items, what, warnings, stored_totals=False),
                        bound_tax,
                        what,
                        warnings,
                    ),
                    "showPaymentInstructions": _bool(row.get("show_payment_instructions"), True),
                    "selectedPaymentMethods": _selected_methods(
                        row.get("selected_payment_methods"), what, warnings
                    ),
                    "taxEnabled": None
                    if row.get("tax_enabled") is None
                    else bool(row["tax_enabled"]),
                    "taxRate": _tax_rate(row.get("tax_rate"), what, warnings),
                    "taxName": _fit(row.get("tax_name"), 50, f"{what} tax name", warnings),
                    "autoEmailEnabled": _bool(row.get("auto_email_enabled"), False),
                    "emailSubjectTemplate": _fit(
                        row.get("email_subject_template"), 500, f"{what} email subject", warnings
                    ),
                    "emailBodyTemplate": _fit(
                        row.get("email_body_template"), 10_000, f"{what} email body", warnings
                    ),
                    "nextInvoiceDate": _date(row.get("next_invoice_date")) or created[:10],
                },
            }
        )

    logo = _logo(profile_row.get("logo_path"), warnings)
    if len(warnings) > MAX_WARNINGS:
        extra = len(warnings) - (MAX_WARNINGS - 1)
        del warnings[MAX_WARNINGS - 1 :]
        warnings.append(f"...and {extra} more adjustments.")
    source_name = profile.get("businessName") or profile.get("name") or "Invoice Machine"
    return {
        "manifest": {
            "format": FORMAT,
            "formatVersion": FORMAT_VERSION,
            "createdAt": now,
            "sourceName": _fit(f"Invoice Machine: {source_name}", 255, "The source name", []),
        },
        "profile": profile,
        "clients": clients,
        "invoices": invoices,
        "recurringSchedules": schedules,
        "logo": logo,
        "warnings": [warning[:MAX_WARNING_LENGTH] for warning in warnings],
    }
