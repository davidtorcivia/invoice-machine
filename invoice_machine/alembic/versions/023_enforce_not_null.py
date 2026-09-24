"""Enforce the models' NOT NULL columns in the database and drop redundant indexes.

The models declared these columns NOT NULL but the migrations left them
nullable. SQLite can only add NOT NULL by rebuilding the table, so each table is
backfilled with its model default and rebuilt. env.py runs migrations with
foreign keys off, which keeps the rebuild's DROP TABLE from cascading.

Revision ID: 023_enforce_not_null
Revises: 022_permanent_pay_links
Create Date: 2026-09-24

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger("alembic.runtime.migration")

revision: str = "023_enforce_not_null"
down_revision: str | None = "022_permanent_pay_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = "CURRENT_TIMESTAMP"

# (column, existing type, SQL value for existing NULLs). Values are the model
# defaults, except flags the code reads as off when NULL, which stay off.
_COLUMNS: dict[str, list[tuple[str, sa.types.TypeEngine, str]]] = {
    "business_profile": [
        ("country", sa.String(100), "'United States'"),
        ("accent_color", sa.String(7), "'#16a34a'"),
        ("default_payment_terms_days", sa.Integer(), "30"),
        ("theme_preference", sa.String(20), "'system'"),
        ("backup_enabled", sa.Integer(), "0"),
        ("backup_retention_days", sa.Integer(), "30"),
        ("backup_s3_enabled", sa.Integer(), "0"),
        ("default_tax_enabled", sa.Integer(), "0"),
        ("default_tax_rate", sa.DECIMAL(5, 2), "0"),
        ("default_tax_name", sa.String(50), "'Tax'"),
        ("smtp_enabled", sa.Integer(), "0"),
        ("smtp_port", sa.Integer(), "587"),
        ("smtp_use_tls", sa.Integer(), "0"),
        ("created_at", sa.DateTime(), _NOW),
        ("updated_at", sa.DateTime(), _NOW),
    ],
    "clients": [
        ("payment_terms_days", sa.Integer(), "30"),
        ("created_at", sa.DateTime(), _NOW),
        ("updated_at", sa.DateTime(), _NOW),
    ],
    "invoice_items": [
        ("quantity", sa.Numeric(12, 3), "1"),
        ("unit_type", sa.String(10), "'qty'"),
        ("sort_order", sa.Integer(), "0"),
    ],
    "invoices": [
        ("status", sa.String(20), "'draft'"),
        ("document_type", sa.String(20), "'invoice'"),
        ("show_payment_instructions", sa.Integer(), "0"),
        ("payment_terms_days", sa.Integer(), "30"),
        ("currency_code", sa.String(3), "'USD'"),
        ("subtotal", sa.DECIMAL(10, 2), "0"),
        ("tax_enabled", sa.Integer(), "0"),
        ("tax_rate", sa.DECIMAL(5, 2), "0"),
        ("tax_name", sa.String(50), "'Tax'"),
        ("tax_amount", sa.DECIMAL(10, 2), "0"),
        ("total", sa.DECIMAL(10, 2), "0"),
        # The issue date sorts an undated row with its peers, not as the newest.
        ("created_at", sa.DateTime(), f"COALESCE(issue_date || ' 00:00:00', {_NOW})"),
        ("updated_at", sa.DateTime(), _NOW),
    ],
    "payments": [
        ("created_at", sa.DateTime(), _NOW),
        ("updated_at", sa.DateTime(), _NOW),
    ],
    "recurring_schedules": [
        ("schedule_day", sa.Integer(), "1"),
        ("currency_code", sa.String(3), "'USD'"),
        ("payment_terms_days", sa.Integer(), "30"),
        # Not the model default of 1: the scheduler skips NULL rows today, and
        # reactivating them here would start issuing invoices nobody asked for.
        ("is_active", sa.Integer(), "0"),
        ("created_at", sa.DateTime(), _NOW),
        ("updated_at", sa.DateTime(), _NOW),
    ],
    "sessions": [("created_at", sa.DateTime(), _NOW)],
    "users": [("created_at", sa.DateTime(), _NOW)],
}

# Each is a leading-column prefix of a composite index, covered by a UNIQUE
# column constraint, or on a column only ever searched with a leading wildcard.
_REDUNDANT_INDEXES: list[tuple[str, str, str, bool]] = [
    ("idx_clients_email", "clients", "email", False),
    ("idx_clients_name", "clients", "name", False),
    ("idx_clients_business_name", "clients", "business_name", False),
    ("idx_invoices_status", "invoices", "status", False),
    ("idx_invoices_client", "invoices", "client_id", False),
    ("idx_invoices_date", "invoices", "issue_date", False),
    ("idx_recurring_active", "recurring_schedules", "is_active", False),
    ("idx_sessions_token", "sessions", "token", True),
]


def _trigger_sql(conn: sa.Connection, table: str) -> dict[str, str]:
    rows = conn.execute(
        sa.text("SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = :t"),
        {"t": table},
    )
    return {row.name: row.sql for row in rows}


def upgrade() -> None:
    conn = op.get_bind()

    # Dropped first, or the rebuild below would reflect and recreate them.
    for name, _table, _column, _unique in _REDUNDANT_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")

    for table, columns in _COLUMNS.items():
        for column, _type, value in columns:
            filled = conn.execute(
                sa.text(f"UPDATE {table} SET {column} = {value} WHERE {column} IS NULL")
            ).rowcount
            if filled:
                logger.warning("Backfilled %s NULL %s.%s with %s", filled, table, column, value)

        # The rebuild drops the table's triggers, including the FTS sync ones.
        triggers = _trigger_sql(conn, table)
        with op.batch_alter_table(table) as batch_op:
            for column, type_, _value in columns:
                batch_op.alter_column(column, existing_type=type_, nullable=False)
        for sql in triggers.values():
            conn.exec_driver_sql(sql)
        missing = triggers.keys() - _trigger_sql(conn, table).keys()
        if missing:
            raise RuntimeError(f"Triggers on {table} were not restored: {sorted(missing)}")


def downgrade() -> None:
    # NOT NULL stays: relaxing it would rebuild every table again for no gain.
    for name, table, column, unique in _REDUNDANT_INDEXES:
        kind = "UNIQUE INDEX" if unique else "INDEX"
        op.execute(f"CREATE {kind} IF NOT EXISTS {name} ON {table} ({column})")
