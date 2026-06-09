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

    # SQLite's batch_alter rebuilds invoice_items (create/copy/drop/rename), which
    # silently drops the FTS sync triggers created in migration 008. Recreate them
    # so new/edited line items keep flowing into invoice_items_fts. (IF NOT EXISTS
    # keeps this safe if the table was rebuilt some other way.)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS invoice_items_fts_insert AFTER INSERT ON invoice_items BEGIN
            INSERT INTO invoice_items_fts(rowid, description)
            VALUES (new.id, new.description);
        END
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS invoice_items_fts_delete AFTER DELETE ON invoice_items BEGIN
            DELETE FROM invoice_items_fts WHERE rowid = old.id;
        END
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS invoice_items_fts_update AFTER UPDATE ON invoice_items BEGIN
            DELETE FROM invoice_items_fts WHERE rowid = old.id;
            INSERT INTO invoice_items_fts(rowid, description)
            VALUES (new.id, new.description);
        END
    """)


def downgrade() -> None:
    with op.batch_alter_table("invoice_items") as batch_op:
        batch_op.alter_column(
            "quantity",
            existing_type=sa.Numeric(12, 3),
            type_=sa.Integer(),
            existing_nullable=False,
        )
