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
        """Accept both numeric and string input, always store as string."""
        return str(v)
