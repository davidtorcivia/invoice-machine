"""Add recurring schedules table.

Revision ID: 002_recurring
Revises: 001_initial
Create Date: 2025-01-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_recurring"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recurring_schedules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("schedule_day", sa.Integer(), default=1),
        sa.Column("currency_code", sa.String(3), default="USD"),
        sa.Column("payment_terms_days", sa.Integer(), default=30),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("line_items", sa.Text(), nullable=True),
        # Tax settings
        sa.Column("tax_enabled", sa.Integer(), nullable=True),
        sa.Column("tax_rate", sa.DECIMAL(5, 2), nullable=True),
        sa.Column("tax_name", sa.String(50), nullable=True),
        # Schedule status
        sa.Column("is_active", sa.Integer(), default=1),
        sa.Column("next_invoice_date", sa.Date(), nullable=False),
        sa.Column("last_invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_recurring_client", "recurring_schedules", ["client_id"])
    op.create_index("idx_recurring_next_date", "recurring_schedules", ["next_invoice_date"])
    op.create_index("idx_recurring_active", "recurring_schedules", ["is_active"])


def downgrade() -> None:
    op.drop_table("recurring_schedules")
