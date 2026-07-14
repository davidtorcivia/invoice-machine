"""Exact conversion between Decimal invoice money and provider minor units."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

ZERO_DECIMAL_CURRENCIES = {
    "BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG",
    "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
}
THREE_DECIMAL_CURRENCIES = {"BHD", "JOD", "KWD", "OMR", "TND"}


def currency_exponent(currency_code: str) -> int:
    code = currency_code.upper()
    if code in ZERO_DECIMAL_CURRENCIES:
        return 0
    if code in THREE_DECIMAL_CURRENCIES:
        return 3
    return 2


def to_minor_units(amount: Decimal | str | int, currency_code: str) -> int:
    """Convert exactly, rejecting precision the provider cannot represent."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Amount must be a decimal number") from None
    if not value.is_finite() or value < 0:
        raise ValueError("Amount must be finite and non-negative")

    exponent = currency_exponent(currency_code)
    scale = Decimal(10) ** exponent
    scaled = value * scale
    if scaled != scaled.to_integral_value():
        raise ValueError(
            f"{currency_code.upper()} supports at most {exponent} decimal places"
        )
    return int(scaled)


def from_minor_units(amount_minor: int, currency_code: str) -> Decimal:
    exponent = currency_exponent(currency_code)
    return Decimal(amount_minor) / (Decimal(10) ** exponent)
