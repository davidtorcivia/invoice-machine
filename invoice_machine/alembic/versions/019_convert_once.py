"""A quote can convert to at most one invoice.

Revision ID: 019_convert_once
Revises: 018_credential_widths
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "019_convert_once"
down_revision: str | None = "018_credential_widths"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    dups = conn.execute(
        sa.text(
            """
            SELECT converted_from_invoice_id, MIN(id) AS keep_id
            FROM invoices
            WHERE converted_from_invoice_id IS NOT NULL
            GROUP BY converted_from_invoice_id
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    for src, keep_id in dups:
        conn.execute(
            sa.text(
                """
                UPDATE invoices
                SET converted_from_invoice_id = NULL
                WHERE converted_from_invoice_id = :src AND id != :keep
                """
            ),
            {"src": src, "keep": keep_id},
        )

    op.create_index(
        "uq_invoices_converted_from",
        "invoices",
        ["converted_from_invoice_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_invoices_converted_from", table_name="invoices")
