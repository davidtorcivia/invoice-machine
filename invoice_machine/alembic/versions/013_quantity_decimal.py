"""Allow fractional line-item quantities (e.g. 1.5 hours).

Changes invoice_items.quantity from INTEGER to NUMERIC(12,3). SQLite requires a
batch (table-rebuild) migration to change a column type.

Revision ID: 013_quantity_decimal
Revises: 012_paid_at_email_templates
Create Date: 2026-05-28

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "013_quantity_decimal"
down_revision: str | None = "012_paid_at_email_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("invoice_items") as batch_op:
        batch_op.alter_column(
            "quantity",
            existing_type=sa.Integer(),
            type_=sa.Numeric(12, 3),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("invoice_items") as batch_op:
        batch_op.alter_column(
            "quantity",
            existing_type=sa.Numeric(12, 3),
            type_=sa.Integer(),
            existing_nullable=False,
        )
