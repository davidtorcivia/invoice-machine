#!/usr/bin/env python
"""Generate golden outputs for the pure money and date arithmetic.

    python tests/golden/generate.py          # rewrite tests/golden/*.json
    python tests/golden/generate.py --check  # fail if anything drifted

These files pin the exact output of the functions that decide what a customer
is charged: rounding, minor-unit conversion, FX, quantity coercion, and due
dates. Ordinary unit tests assert a handful of cases; a golden file pins the
whole matrix, including the boundaries nobody thinks to assert.

Two properties make these worth more than the tests around them:

  * Errors are recorded as "ExceptionType: message", so a refactor that changes
    which exception a bad input raises -- or its wording -- breaks the hash.
    Error identity is behavior, and it is the part tests most often miss.
  * The matrix covers the three minor-unit families together. JPY has no minor
    unit, KWD has three decimal places, and everything else has two. Code that
    assumes cents is correct for most of the matrix and silently wrong for the
    rest.

Determinism: no clock, no randomness, no database. Sorted keys, fixed
separators, trailing newline. Regenerating on an unchanged tree is a no-op.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from invoice_machine.service.common import (  # noqa: E402
    calculate_due_date,
    convert_to_base,
    format_currency,
    format_quantity,
    line_item_total,
    normalize_line_items,
    quantize_money,
    quantize_quantity,
)
from invoice_machine.service.stripe_links import (  # noqa: E402
    currency_exponent,
    from_stripe_amount,
    to_stripe_amount,
)

GOLDEN_DIR = Path(__file__).parent

# One representative of each minor-unit family, plus the majors.
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "KWD", "BHD", "ISK"]

# Rounding boundaries, sub-cent dust, negatives, and magnitudes big enough to
# expose a float that sneaked into a Decimal path.
AMOUNTS = [
    "0", "0.001", "0.004", "0.005", "0.006", "0.01", "0.015", "0.025",
    "1", "1.005", "1.045", "1.055", "2.675", "10.101", "99.994", "99.995",
    "100", "1234.567", "999999.994", "999999.995", "1000000",
    "-0.005", "-1.005", "-99.995",
]

QUANTITIES = ["1", "0.25", "1.5", "0.0005", "0.001", "2.9995", "3.0004", "0", "-1", "abc"]


def attempt(fn, *args, **kwargs):
    """Call fn, returning either its value or a stable rendering of its error.

    The exception type and message are part of the observable contract, so they
    belong in the golden alongside the successful results.
    """
    try:
        return render(fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001 - recording the error IS the point
        return f"!{type(exc).__name__}: {exc}"


def render(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [render(v) for v in value]
    if isinstance(value, dict):
        return {k: render(v) for k, v in value.items()}
    return value


def build_money() -> dict:
    return {
        "quantize_money": {a: attempt(quantize_money, a) for a in AMOUNTS},
        "line_item_total": {
            f"{p} x {q}": attempt(line_item_total, p, q)
            for p in ["0.01", "1.005", "19.99", "1234.567", "-5.005"]
            for q in ["1", "0.25", "1.5", "3", "0.001"]
        },
        "format_currency": {
            f"{a} {c}": attempt(format_currency, a, c)
            for a in ["0", "1234.5", "1234.567", "-99.995", "1000000"]
            for c in CURRENCIES
        },
        "convert_to_base": {
            f"{a} @ {r}": attempt(convert_to_base, a, None if r == "None" else Decimal(r))
            for a in ["0", "100", "1234.567", "-50.005"]
            for r in ["None", "1", "0.8712", "1.10345", "157.25"]
        },
    }


def build_quantities() -> dict:
    return {
        "quantize_quantity": {q: attempt(quantize_quantity, q) for q in QUANTITIES},
        "format_quantity": {
            q: attempt(format_quantity, q)
            for q in ["1", "1.0", "1.50", "0.25", "2.000", "0", "0.001", "1234.5"]
        },
        "normalize_line_items": {
            "typical": attempt(normalize_line_items, [
                {"description": "Design", "quantity": "2", "unit_price": "150.00"},
                {"description": "Hours", "quantity": 1.5, "unit_price": 99.99,
                 "unit_type": "hours"},
            ]),
            "empty": attempt(normalize_line_items, []),
            "none": attempt(normalize_line_items, None),
            "zero_quantity": attempt(normalize_line_items, [
                {"description": "x", "quantity": "0", "unit_price": "1"}]),
            "negative_price": attempt(normalize_line_items, [
                {"description": "x", "quantity": "1", "unit_price": "-1"}]),
            "missing_description": attempt(normalize_line_items, [
                {"quantity": "1", "unit_price": "1"}]),
            "bad_unit_type": attempt(normalize_line_items, [
                {"description": "x", "quantity": "1", "unit_price": "1",
                 "unit_type": "furlongs"}]),
        },
    }


def build_stripe() -> dict:
    return {
        "currency_exponent": {c: attempt(currency_exponent, c) for c in CURRENCIES},
        "to_stripe_amount": {
            f"{a} {c}": attempt(to_stripe_amount, Decimal(a), c)
            for a in ["0", "0.001", "0.005", "0.01", "1", "1.005", "19.99",
                      "100", "1234.567", "-1"]
            for c in CURRENCIES
        },
        "from_stripe_amount": {
            f"{n} {c}": attempt(from_stripe_amount, n, c)
            for n in [0, 1, 5, 100, 1999, 123456, -100]
            for c in CURRENCIES
        },
    }


def build_dates() -> dict:
    issues = [date(2025, 1, 15), date(2025, 1, 31), date(2024, 2, 29), date(2025, 12, 31)]
    return {
        "calculate_due_date": {
            f"{d.isoformat()} +{t}": attempt(calculate_due_date, d, t)
            for d in issues
            for t in [0, 1, 7, 14, 30, 45, 60, 90, 365, None]
        },
        "calculate_due_date_explicit_wins": {
            "2025-01-15 terms=30 explicit=2025-02-01": attempt(
                calculate_due_date, date(2025, 1, 15), 30, date(2025, 2, 1)),
        },
    }


BUILDERS = {
    "money.json": build_money,
    "quantities.json": build_quantities,
    "stripe_amounts.json": build_stripe,
    "due_dates.json": build_dates,
}


def serialize(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if any golden differs instead of rewriting it")
    args = ap.parse_args()

    drifted = []
    for name, builder in BUILDERS.items():
        path = GOLDEN_DIR / name
        text = serialize(builder())
        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != text:
                drifted.append(name)
        else:
            path.write_text(text, encoding="utf-8")
            print(f"[golden] wrote {path.relative_to(GOLDEN_DIR.parents[1])}")

    if args.check:
        if drifted:
            print("[golden] DRIFTED: " + ", ".join(drifted), file=sys.stderr)
            print("[golden] If the change is intended, rerun without --check and "
                  "review the diff as a behavior change, not a formatting one.",
                  file=sys.stderr)
            return 1
        print("[golden] all goldens match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
