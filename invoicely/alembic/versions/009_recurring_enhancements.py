"""Add enhancements to recurring_schedules table.

Adds scheduling improvements (yearly month, quarterly month offset),
payment method selection, auto-email feature, and notes toggle.

Revision ID: 009_recurring_enhancements
Revises: 008_line_items_fts
Create Date: 2026-01-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "009_recurring_enhancements"
down_revision: Union[str, None] = "008_line_items_fts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check existing columns to make migration idempotent
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("recurring_schedules")]

    # Scheduling improvements
    if "schedule_month" not in columns:
        op.add_column(
            "recurring_schedules",
            sa.Column("schedule_month", sa.Integer(), nullable=True),
        )

    if "quarter_month" not in columns:
        op.add_column(
            "recurring_schedules",
            sa.Column("quarter_month", sa.Integer(), server_default="1", nullable=False),
        )

    # Payment method selection (like invoices)
    if "show_payment_instructions" not in columns:
        op.add_column(
            "recurring_schedules",
            sa.Column("show_payment_instructions", sa.Integer(), server_default="1", nullable=False),
        )

    if "selected_payment_methods" not in columns:
        op.add_column(
            "recurring_schedules",
            sa.Column("selected_payment_methods", sa.Text(), nullable=True),
        )

    # Auto-email feature
    if "auto_email_enabled" not in columns:
        op.add_column(
            "recurring_schedules",
            sa.Column("auto_email_enabled", sa.Integer(), server_default="0", nullable=False),
        )

    if "email_subject_template" not in columns:
        op.add_column(
            "recurring_schedules",
            sa.Column("email_subject_template", sa.String(500), nullable=True),
        )

    if "email_body_template" not in columns:
        op.add_column(
            "recurring_schedules",
            sa.Column("email_body_template", sa.Text(), nullable=True),
        )

    # Notes toggle
    if "use_default_notes" not in columns:
        op.add_column(
            "recurring_schedules",
            sa.Column("use_default_notes", sa.Integer(), server_default="1", nullable=False),
        )


def downgrade() -> None:
    op.drop_column("recurring_schedules", "use_default_notes")
    op.drop_column("recurring_schedules", "email_body_template")
    op.drop_column("recurring_schedules", "email_subject_template")
    op.drop_column("recurring_schedules", "auto_email_enabled")
    op.drop_column("recurring_schedules", "selected_payment_methods")
    op.drop_column("recurring_schedules", "show_payment_instructions")
    op.drop_column("recurring_schedules", "quarter_month")
    op.drop_column("recurring_schedules", "schedule_month")
