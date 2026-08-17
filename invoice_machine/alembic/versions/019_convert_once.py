"""A quote can convert to at most one invoice.

Revision ID: 019_convert_once
Revises: 018_credential_widths
Create Date: 2026-08-17

"""

from collections.abc import Sequence

from alembic import op

revision: str = "019_convert_once"
down_revision: str | None = "018_credential_widths"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_invoices_converted_from",
        "invoices",
        ["converted_from_invoice_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_invoices_converted_from", table_name="invoices")
