"""Shared Pydantic schemas used across API modules."""

from pydantic import BaseModel, Field, field_validator


class LineItemCreate(BaseModel):
    """Line item input schema for invoices and recurring schedules."""

    description: str = Field(..., min_length=1, max_length=2000)
    quantity: int = Field(1, ge=1, le=10000)
    unit_type: str = Field("qty", pattern="^(qty|hours)$")
    unit_price: str

    @field_validator("unit_price", mode="before")
    @classmethod
    def coerce_unit_price(cls, v):
        """Accept both numeric and string input, always store as string."""
        return str(v)
