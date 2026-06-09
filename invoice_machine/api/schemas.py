"""Shared Pydantic schemas used across API modules."""

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class LineItemCreate(BaseModel):
    """Line item input schema for invoices and recurring schedules."""

    description: str = Field(..., min_length=1, max_length=2000)
    # Decimal to support fractional hours (e.g. 1.5, 0.25).
    quantity: Decimal = Field(Decimal("1"), gt=0, le=10000)
    unit_type: str = Field("qty", pattern="^(qty|hours)$")
    unit_price: str

    @field_validator("unit_price", mode="before")
    @classmethod
    def coerce_unit_price(cls, v):
        """Accept numeric or string input; reject non-numeric/negative values.

        Stored as a string so the service layer's ``Decimal(str(...))`` round-trips
        exactly. Without this, garbage like ``"abc"`` reached the service and raised
        an uncaught ``decimal.InvalidOperation`` (HTTP 500), or a negative price was
        persisted into a recurring schedule's stored line items.
        """
        try:
            amount = Decimal(str(v))
        except (ArithmeticError, ValueError, TypeError):
            raise ValueError("Unit price must be a number") from None
        if not amount.is_finite():
            raise ValueError("Unit price must be a finite number")
        if amount < 0:
            raise ValueError("Unit price cannot be negative")
        return str(amount)
