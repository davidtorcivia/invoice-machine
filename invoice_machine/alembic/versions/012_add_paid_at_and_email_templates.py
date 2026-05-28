"""Add invoices.paid_at and business_profile email template columns.

- invoices.paid_at: timestamp of the paid transition, for cash-basis reporting.
- business_profile.email_subject_template / email_body_template: these existed
  only in the ORM model and the legacy ad-hoc migration, with no Alembic
  migration (schema drift). Added here idempotently so a database built purely
  from `alembic upgrade head` matches the models.

Revision ID: 012_paid_at_email_templates
Revises: 011_add_bot_api_key
Create Date: 2026-05-28

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "012_paid_at_email_templates"
down_revision: str | None = "011_add_bot_api_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    invoice_columns = _columns("invoices")
    if "paid_at" not in invoice_columns:
        op.add_column("invoices", sa.Column("paid_at", sa.DateTime(), nullable=True))

    profile_columns = _columns("business_profile")
    if "email_subject_template" not in profile_columns:
        op.add_column(
            "business_profile",
            sa.Column("email_subject_template", sa.String(500), nullable=True),
        )
    if "email_body_template" not in profile_columns:
        op.add_column(
            "business_profile",
            sa.Column("email_body_template", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("business_profile", "email_body_template")
    op.drop_column("business_profile", "email_subject_template")
    op.drop_column("invoices", "paid_at")
