"""Let a manual payment carry an idempotency key so retries cannot double-record.

`record_manual_payment` refuses anything exceeding the outstanding balance, so a
repeated *full* payment was already blocked. A repeated *partial* payment was
not: recording 40.00 twice against a 100.00 invoice left the invoice showing
80.00 paid from one real payment. That is exactly the case a retried tool call
or a double-submitted form hits.

The column is nullable, so every existing payment stays valid, and the unique
index is scoped to (provider, idempotency_key) - NULLs do not collide, so
unkeyed payments are unaffected and callers can still record two genuinely
identical payments by supplying different keys.

Revision ID: 015_payment_idempotency
Revises: 014_payments_reminders
Create Date: 2026-07-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015_payment_idempotency"
down_revision: str | None = "014_payments_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("payments") as batch_op:
        batch_op.add_column(sa.Column("idempotency_key", sa.String(255), nullable=True))

    op.create_index(
        "uq_payments_provider_idempotency_key",
        "payments",
        ["provider", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_payments_provider_idempotency_key", table_name="payments")

    with op.batch_alter_table("payments") as batch_op:
        batch_op.drop_column("idempotency_key")
