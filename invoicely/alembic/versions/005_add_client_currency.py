"""Add preferred_currency to clients table.

Revision ID: 005_client_currency
Revises: 004_composite_indexes
Create Date: 2026-01-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "005_client_currency"
down_revision: Union[str, None] = "004_composite_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("preferred_currency", sa.String(3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clients", "preferred_currency")
