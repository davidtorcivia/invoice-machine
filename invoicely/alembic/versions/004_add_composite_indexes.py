"""Add composite database indexes for query optimization.

Revision ID: 004_composite_indexes
Revises: 003_fts5
Create Date: 2026-01-17

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_composite_indexes"
down_revision: Union[str, None] = "003_fts5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Get existing indexes to make migration idempotent
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    # Helper to check if index exists
    def index_exists(table_name, index_name):
        indexes = inspector.get_indexes(table_name)
        return any(idx["name"] == index_name for idx in indexes)

    # Composite indexes for invoices - common query patterns
    if not index_exists("invoices", "idx_invoices_status_deleted"):
        op.create_index(
            "idx_invoices_status_deleted",
            "invoices",
            ["status", "deleted_at"],
        )
    if not index_exists("invoices", "idx_invoices_client_status"):
        op.create_index(
            "idx_invoices_client_status",
            "invoices",
            ["client_id", "status"],
        )
    if not index_exists("invoices", "idx_invoices_date_status"):
        op.create_index(
            "idx_invoices_date_status",
            "invoices",
            ["issue_date", "status"],
        )

    # Composite index for recurring schedules - processing due schedules
    if not index_exists("recurring_schedules", "idx_recurring_active_next_date"):
        op.create_index(
            "idx_recurring_active_next_date",
            "recurring_schedules",
            ["is_active", "next_invoice_date"],
        )


def downgrade() -> None:
    op.drop_index("idx_invoices_status_deleted", table_name="invoices")
    op.drop_index("idx_invoices_client_status", table_name="invoices")
    op.drop_index("idx_invoices_date_status", table_name="invoices")
    op.drop_index("idx_recurring_active_next_date", table_name="recurring_schedules")
