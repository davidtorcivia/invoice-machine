"""Let a recorded payment carry an idempotency key so retries cannot double-record.

`record_payment` refuses anything exceeding the outstanding balance, so a
repeated *full* payment was already blocked. A repeated *partial* payment was
not: recording 40.00 twice against a 100.00 invoice left the invoice showing
80.00 paid from one real payment. That is exactly the case a retried tool call
or a double-submitted form hits.

The column is nullable, so every existing payment stays valid. The unique index
covers the key alone rather than being scoped by provider: manually recorded
payments leave `provider` NULL, and a unique index treats NULLs as distinct, so
a (provider, idempotency_key) index would happily accept two NULL-provider rows
sharing a key and enforce nothing. NULL keys still do not collide, so unkeyed
payments are unaffected and callers can record two genuinely identical payments
by supplying different keys.

A unique index rather than a UniqueConstraint like its neighbours: SQLite cannot
add a constraint in place, so a constraint would rebuild the whole payments
table. CREATE UNIQUE INDEX needs no rebuild and enforces the same thing.

Revision ID: 017_payment_idempotency
Revises: 016_business_timezone
Create Date: 2026-07-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "017_payment_idempotency"
down_revision: str | None = "016_business_timezone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("payments") as batch_op:
        batch_op.add_column(sa.Column("idempotency_key", sa.String(255), nullable=True))

    op.create_index(
        "uq_payments_idempotency_key",
        "payments",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_payments_idempotency_key", table_name="payments")

    with op.batch_alter_table("payments") as batch_op:
        batch_op.drop_column("idempotency_key")
