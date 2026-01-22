"""Add default_currency_code to business_profile.

Revision ID: 007_default_currency
Revises: 006_search_indexes
Create Date: 2026-01-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "007_default_currency"
down_revision: Union[str, None] = "006_search_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if column already exists (make migration idempotent)
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    columns = [col["name"] for col in inspector.get_columns("business_profile")]

    if "default_currency_code" not in columns:
        op.add_column(
            "business_profile",
            sa.Column("default_currency_code", sa.String(3), server_default="USD", nullable=False),
        )


def downgrade() -> None:
    op.drop_column("business_profile", "default_currency_code")
