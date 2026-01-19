"""Add FTS5 full-text search tables and triggers.

Revision ID: 003_fts5
Revises: 002_recurring
Create Date: 2025-01-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_fts5"
down_revision: Union[str, None] = "002_recurring"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create FTS5 virtual table for invoices
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS invoices_fts USING fts5(
            invoice_number,
            client_name,
            client_business,
            notes,
            content='invoices',
            content_rowid='id'
        )
    """)

    # Create FTS5 virtual table for clients
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS clients_fts USING fts5(
            name,
            business_name,
            email,
            notes,
            content='clients',
            content_rowid='id'
        )
    """)

    # Triggers to keep invoices_fts in sync
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS invoices_fts_insert AFTER INSERT ON invoices BEGIN
            INSERT INTO invoices_fts(rowid, invoice_number, client_name, client_business, notes)
            VALUES (new.id, new.invoice_number, new.client_name, new.client_business, new.notes);
        END
    """)

    op.execute("""
        CREATE TRIGGER IF NOT EXISTS invoices_fts_delete AFTER DELETE ON invoices BEGIN
            INSERT INTO invoices_fts(invoices_fts, rowid, invoice_number, client_name, client_business, notes)
            VALUES ('delete', old.id, old.invoice_number, old.client_name, old.client_business, old.notes);
        END
    """)

    op.execute("""
        CREATE TRIGGER IF NOT EXISTS invoices_fts_update AFTER UPDATE ON invoices BEGIN
            INSERT INTO invoices_fts(invoices_fts, rowid, invoice_number, client_name, client_business, notes)
            VALUES ('delete', old.id, old.invoice_number, old.client_name, old.client_business, old.notes);
            INSERT INTO invoices_fts(rowid, invoice_number, client_name, client_business, notes)
            VALUES (new.id, new.invoice_number, new.client_name, new.client_business, new.notes);
        END
    """)

    # Triggers to keep clients_fts in sync
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS clients_fts_insert AFTER INSERT ON clients BEGIN
            INSERT INTO clients_fts(rowid, name, business_name, email, notes)
            VALUES (new.id, new.name, new.business_name, new.email, new.notes);
        END
    """)

    op.execute("""
        CREATE TRIGGER IF NOT EXISTS clients_fts_delete AFTER DELETE ON clients BEGIN
            INSERT INTO clients_fts(clients_fts, rowid, name, business_name, email, notes)
            VALUES ('delete', old.id, old.name, old.business_name, old.email, old.notes);
        END
    """)

    op.execute("""
        CREATE TRIGGER IF NOT EXISTS clients_fts_update AFTER UPDATE ON clients BEGIN
            INSERT INTO clients_fts(clients_fts, rowid, name, business_name, email, notes)
            VALUES ('delete', old.id, old.name, old.business_name, old.email, old.notes);
            INSERT INTO clients_fts(rowid, name, business_name, email, notes)
            VALUES (new.id, new.name, new.business_name, new.email, new.notes);
        END
    """)

    # Rebuild FTS tables to sync with existing data
    # For external content FTS tables (content=), use the 'rebuild' command
    # This reads from the content table and builds the inverted index correctly
    conn = op.get_bind()

    # Check if there's data to index
    invoices_count = conn.execute(sa.text("SELECT COUNT(*) FROM invoices")).scalar()
    if invoices_count > 0:
        op.execute("INSERT INTO invoices_fts(invoices_fts) VALUES('rebuild')")

    clients_count = conn.execute(sa.text("SELECT COUNT(*) FROM clients")).scalar()
    if clients_count > 0:
        op.execute("INSERT INTO clients_fts(clients_fts) VALUES('rebuild')")


def downgrade() -> None:
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS invoices_fts_insert")
    op.execute("DROP TRIGGER IF EXISTS invoices_fts_delete")
    op.execute("DROP TRIGGER IF EXISTS invoices_fts_update")
    op.execute("DROP TRIGGER IF EXISTS clients_fts_insert")
    op.execute("DROP TRIGGER IF EXISTS clients_fts_delete")
    op.execute("DROP TRIGGER IF EXISTS clients_fts_update")

    # Drop FTS tables
    op.execute("DROP TABLE IF EXISTS invoices_fts")
    op.execute("DROP TABLE IF EXISTS clients_fts")
