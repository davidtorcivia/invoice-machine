"""Backfill payment records for invoices settled before payment tracking existed.

Migration 014 added ``invoices.amount_paid`` defaulting to 0. Invoices already
marked "paid" therefore reported their full total as still outstanding, which is
both wrong on screen and wrong in the aging report.

The fix records one payment per settled invoice rather than only setting
``amount_paid``. The design invariant is that ``amount_paid`` is a cache of
SUM(payments); setting the cache alone would leave it unbacked, so the first
payment recorded against such an invoice would recompute it from an empty ledger
and silently un-pay a settled invoice.

Each backfilled row is labelled in ``notes`` so it is never mistaken for an
observed transaction, and carries no method or reference because none is known.
The payment date is the invoice's ``paid_at`` where recorded, otherwise its
issue date.

Revision ID: 015_backfill_paid
Revises: 014_payments_reporting
Create Date: 2026-07-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015_backfill_paid"
down_revision: str | None = "014_payments_reporting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BACKFILL_NOTE = "Backfilled: invoice was marked paid before payment tracking existed."


def upgrade() -> None:
    conn = op.get_bind()

    # Only invoices that are marked paid, have a total, and have no payments yet.
    # Re-running is a no-op because the second condition stops matching.
    rows = conn.execute(
        sa.text(
            """
            SELECT id, total, paid_at, issue_date, currency_code
            FROM invoices
            WHERE status = 'paid'
              AND total > 0
              AND id NOT IN (SELECT DISTINCT invoice_id FROM payments)
            """
        )
    ).fetchall()

    for row in rows:
        payment_date = row.paid_at or row.issue_date
        # paid_at is a datetime; payments.payment_date is a date.
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

    # Sync the cache for every invoice, so amount_paid == SUM(payments) holds
    # from here on regardless of how the row got there.
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
