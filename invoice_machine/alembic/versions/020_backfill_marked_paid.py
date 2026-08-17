"""Backfill payment rows for invoices marked paid after 015 with an empty ledger.

Revision ID: 020_backfill_marked_paid
Revises: 019_convert_once
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020_backfill_marked_paid"
down_revision: str | None = "019_convert_once"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BACKFILL_NOTE = "Marked paid"


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT id, total, paid_at, issue_date, currency_code
            FROM invoices
            WHERE status = 'paid'
              AND document_type = 'invoice'
              AND total > 0
              AND id NOT IN (SELECT DISTINCT invoice_id FROM payments)
            """
        )
    ).fetchall()

    for row in rows:
        payment_date = row.paid_at or row.issue_date
        if payment_date is not None and hasattr(payment_date, "date"):
            payment_date = payment_date.date()
        elif isinstance(payment_date, str):
            payment_date = payment_date.split(" ")[0].split("T")[0]

        conn.execute(
            sa.text(
                """
                INSERT INTO payments
                    (invoice_id, amount, currency_code, payment_date, notes,
                     created_at, updated_at)
                VALUES
                    (:invoice_id, :amount, :currency_code, :payment_date, :notes,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                "invoice_id": row.id,
                "amount": row.total,
                "currency_code": row.currency_code or "USD",
                "payment_date": payment_date,
                "notes": BACKFILL_NOTE,
            },
        )

    conn.execute(
        sa.text(
            """
            UPDATE invoices
            SET amount_paid = COALESCE(
                (SELECT SUM(amount) FROM payments WHERE payments.invoice_id = invoices.id),
                0
            )
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM payments WHERE notes = :notes"), {"notes": BACKFILL_NOTE})
    conn.execute(
        sa.text(
            """
            UPDATE invoices
            SET amount_paid = COALESCE(
                (SELECT SUM(amount) FROM payments WHERE payments.invoice_id = invoices.id),
                0
            )
            """
        )
    )
