"""Initial schema with all current tables and columns.

Revision ID: 001_initial
Revises:
Create Date: 2025-01-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Get existing tables to make migration idempotent
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Users table
    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("username", sa.String(100), unique=True, nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    # Business profile table (singleton)
    if "business_profile" not in existing_tables:
        op.create_table(
            "business_profile",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("business_name", sa.String(255), nullable=True),
            sa.Column("address_line1", sa.Text(), nullable=True),
            sa.Column("address_line2", sa.Text(), nullable=True),
            sa.Column("city", sa.String(100), nullable=True),
            sa.Column("state", sa.String(100), nullable=True),
            sa.Column("postal_code", sa.String(20), nullable=True),
            sa.Column("country", sa.String(100), default="United States"),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("phone", sa.String(50), nullable=True),
            sa.Column("ein", sa.String(50), nullable=True),
            sa.Column("logo_path", sa.String(500), nullable=True),
            sa.Column("accent_color", sa.String(7), default="#16a34a"),
            sa.Column("default_payment_terms_days", sa.Integer(), default=30),
            sa.Column("default_notes", sa.Text(), nullable=True),
            sa.Column("default_payment_instructions", sa.Text(), nullable=True),
            sa.Column("payment_methods", sa.Text(), nullable=True),
            sa.Column("theme_preference", sa.String(20), default="system"),
            sa.Column("mcp_api_key", sa.String(64), nullable=True),
            sa.Column("app_base_url", sa.String(500), nullable=True),
            # Backup settings
            sa.Column("backup_enabled", sa.Integer(), default=1),
            sa.Column("backup_retention_days", sa.Integer(), default=30),
            sa.Column("backup_s3_enabled", sa.Integer(), default=0),
            sa.Column("backup_s3_config", sa.Text(), nullable=True),
            # Tax settings
            sa.Column("default_tax_enabled", sa.Integer(), default=0),
            sa.Column("default_tax_rate", sa.DECIMAL(5, 2), default=0.00),
            sa.Column("default_tax_name", sa.String(50), default="Tax"),
            # SMTP settings
            sa.Column("smtp_enabled", sa.Integer(), default=0),
            sa.Column("smtp_host", sa.String(255), nullable=True),
            sa.Column("smtp_port", sa.Integer(), default=587),
            sa.Column("smtp_username", sa.String(255), nullable=True),
            sa.Column("smtp_password", sa.String(255), nullable=True),
            sa.Column("smtp_from_email", sa.String(255), nullable=True),
            sa.Column("smtp_from_name", sa.String(255), nullable=True),
            sa.Column("smtp_use_tls", sa.Integer(), default=1),
            # Timestamps
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    # Clients table
    if "clients" not in existing_tables:
        op.create_table(
            "clients",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("business_name", sa.String(255), nullable=True),
            sa.Column("address_line1", sa.Text(), nullable=True),
            sa.Column("address_line2", sa.Text(), nullable=True),
            sa.Column("city", sa.String(100), nullable=True),
            sa.Column("state", sa.String(100), nullable=True),
            sa.Column("postal_code", sa.String(20), nullable=True),
            sa.Column("country", sa.String(100), nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("phone", sa.String(50), nullable=True),
            sa.Column("payment_terms_days", sa.Integer(), default=30),
            sa.Column("notes", sa.Text(), nullable=True),
            # Per-client tax settings
            sa.Column("tax_enabled", sa.Integer(), nullable=True),
            sa.Column("tax_rate", sa.DECIMAL(5, 2), nullable=True),
            sa.Column("tax_name", sa.String(50), nullable=True),
            # Timestamps
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
        op.create_index("idx_clients_deleted", "clients", ["deleted_at"])

    # Invoices table
    if "invoices" not in existing_tables:
        op.create_table(
            "invoices",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("invoice_number", sa.String(50), nullable=False, unique=True),
            sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=True),
            # Denormalized client snapshot
            sa.Column("client_name", sa.String(255), nullable=True),
            sa.Column("client_business", sa.String(255), nullable=True),
            sa.Column("client_address", sa.Text(), nullable=True),
            sa.Column("client_email", sa.String(255), nullable=True),
            # Invoice details
            sa.Column("status", sa.String(20), default="draft"),
            sa.Column("document_type", sa.String(20), default="invoice"),
            sa.Column("client_reference", sa.String(100), nullable=True),
            sa.Column("show_payment_instructions", sa.Integer(), default=1),
            sa.Column("selected_payment_methods", sa.Text(), nullable=True),
            sa.Column("issue_date", sa.Date(), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("payment_terms_days", sa.Integer(), default=30),
            sa.Column("currency_code", sa.String(3), default="USD"),
            sa.Column("subtotal", sa.DECIMAL(10, 2), default=0),
            # Tax fields
            sa.Column("tax_enabled", sa.Integer(), default=0),
            sa.Column("tax_rate", sa.DECIMAL(5, 2), default=0.00),
            sa.Column("tax_name", sa.String(50), default="Tax"),
            sa.Column("tax_amount", sa.DECIMAL(10, 2), default=0.00),
            sa.Column("total", sa.DECIMAL(10, 2), default=0),
            sa.Column("notes", sa.Text(), nullable=True),
            # PDF
            sa.Column("pdf_path", sa.String(500), nullable=True),
            sa.Column("pdf_generated_at", sa.DateTime(), nullable=True),
            # Timestamps
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
        op.create_index("idx_invoices_date", "invoices", ["issue_date"])
        op.create_index("idx_invoices_status", "invoices", ["status"])
        op.create_index("idx_invoices_client", "invoices", ["client_id"])
        op.create_index("idx_invoices_deleted", "invoices", ["deleted_at"])

    # Invoice items table
    if "invoice_items" not in existing_tables:
        op.create_table(
            "invoice_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "invoice_id",
                sa.Integer(),
                sa.ForeignKey("invoices.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("quantity", sa.Integer(), default=1),
            sa.Column("unit_type", sa.String(10), default="qty"),
            sa.Column("unit_price", sa.DECIMAL(10, 2), nullable=False),
            sa.Column("total", sa.DECIMAL(10, 2), nullable=False),
            sa.Column("sort_order", sa.Integer(), default=0),
        )
        op.create_index("idx_items_invoice", "invoice_items", ["invoice_id"])


def downgrade() -> None:
    op.drop_table("invoice_items")
    op.drop_table("invoices")
    op.drop_table("clients")
    op.drop_table("business_profile")
    op.drop_table("users")
