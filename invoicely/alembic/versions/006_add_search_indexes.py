"""Add additional indexes for search and query optimization.

Revision ID: 006_search_indexes
Revises: 005_client_currency
Create Date: 2026-01-18

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_search_indexes"
down_revision: Union[str, None] = "005_client_currency"
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

    # Composite index for getting invoices by client that aren't deleted
    if not index_exists("invoices", "idx_invoices_client_deleted"):
        op.create_index(
            "idx_invoices_client_deleted",
            "invoices",
            ["client_id", "deleted_at"],
        )

    # Client search indexes
    if not index_exists("clients", "idx_clients_email"):
        op.create_index(
            "idx_clients_email",
            "clients",
            ["email"],
        )
    if not index_exists("clients", "idx_clients_name"):
        op.create_index(
            "idx_clients_name",
            "clients",
            ["name"],
        )
    if not index_exists("clients", "idx_clients_business_name"):
        op.create_index(
            "idx_clients_business_name",
            "clients",
            ["business_name"],
        )


def downgrade() -> None:
    op.drop_index("idx_invoices_client_deleted", table_name="invoices")
    op.drop_index("idx_clients_email", table_name="clients")
    op.drop_index("idx_clients_name", table_name="clients")
    op.drop_index("idx_clients_business_name", table_name="clients")
