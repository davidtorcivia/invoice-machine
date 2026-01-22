"""Add FTS5 search for invoice line items.

Revision ID: 008_line_items_fts
Revises: 007_default_currency
Create Date: 2026-01-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "008_line_items_fts"
down_revision: Union[str, None] = "007_default_currency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create FTS5 virtual table for invoice line items
    # Using a regular FTS5 table (not external content) for simplicity
    # This stores its own content, which is easier to manage
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS invoice_items_fts USING fts5(
            description
        )
    """)

    # Triggers to keep invoice_items_fts in sync
    # Using simple DELETE/INSERT for regular FTS5 table (not external content)
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

    # Populate FTS table with existing data (only if empty)
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT COUNT(*) FROM invoice_items_fts"))
    if result.scalar() == 0:
        op.execute("""
            INSERT INTO invoice_items_fts(rowid, description)
            SELECT id, description FROM invoice_items
        """)


def downgrade() -> None:
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS invoice_items_fts_insert")
    op.execute("DROP TRIGGER IF EXISTS invoice_items_fts_delete")
    op.execute("DROP TRIGGER IF EXISTS invoice_items_fts_update")

    # Drop FTS table
    op.execute("DROP TABLE IF EXISTS invoice_items_fts")
