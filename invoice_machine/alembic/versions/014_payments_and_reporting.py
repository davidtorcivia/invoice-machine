"""Add payments, payment links, reminders, quote conversion, and FX rates.

Covers six features that all hang off the same schema change:
- payment tracking / partial payments (``payments`` table + ``invoices.amount_paid``)
- Stripe payment links (``invoices.payment_link_*`` + profile credentials)
- automated payment reminders (profile schedule + per-invoice dedup state)
- quote -> invoice conversion (self-referencing link columns)
- multi-currency consolidated reporting (``invoices.exchange_rate`` + profile rates)

Revision ID: 014_payments_reporting
Revises: 013_quantity_decimal
Create Date: 2026-07-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014_payments_reporting"
down_revision: str | None = "013_quantity_decimal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_columns(table: str) -> set[str]:
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns(table)}


def _existing_tables() -> set[str]:
    from sqlalchemy import inspect

    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _existing_tables()

    if "payments" not in tables:
        op.create_table(
            "payments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "invoice_id",
                sa.Integer(),
                sa.ForeignKey("invoices.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("amount", sa.DECIMAL(10, 2), nullable=False),
            # Snapshot of the invoice currency at payment time so a later
            # currency change on the invoice cannot silently relabel history.
            sa.Column("currency_code", sa.String(3), nullable=False, server_default="USD"),
            sa.Column("payment_date", sa.Date(), nullable=False),
            sa.Column("method", sa.String(50), nullable=True),
            sa.Column("reference", sa.String(255), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            # Set for payments created by a provider webhook rather than by hand.
            sa.Column("provider", sa.String(30), nullable=True),
            sa.Column("external_id", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("idx_payments_invoice", "payments", ["invoice_id"])
        op.create_index("idx_payments_date", "payments", ["payment_date"])
        # Webhook idempotency: the same provider event must never be recorded twice.
        op.create_index(
            "idx_payments_provider_external",
            "payments",
            ["provider", "external_id"],
            unique=True,
        )

    invoice_columns = _existing_columns("invoices")
    # NOTE: the conversion links are plain integers, not declared foreign keys.
    # SQLite cannot add a FK constraint to an existing table via ALTER TABLE, and
    # the model matches this so migrated and create_all schemas stay identical.
    new_invoice_columns = [
        (
            "amount_paid",
            sa.Column("amount_paid", sa.DECIMAL(10, 2), nullable=False, server_default="0"),
        ),
        ("exchange_rate", sa.Column("exchange_rate", sa.DECIMAL(18, 8), nullable=True)),
        ("base_currency_code", sa.Column("base_currency_code", sa.String(3), nullable=True)),
        (
            "converted_from_invoice_id",
            sa.Column("converted_from_invoice_id", sa.Integer(), nullable=True),
        ),
        (
            "converted_to_invoice_id",
            sa.Column("converted_to_invoice_id", sa.Integer(), nullable=True),
        ),
        ("reminders_sent", sa.Column("reminders_sent", sa.Text(), nullable=True)),
        ("last_reminder_sent_at", sa.Column("last_reminder_sent_at", sa.DateTime(), nullable=True)),
        ("payment_link_url", sa.Column("payment_link_url", sa.String(1000), nullable=True)),
        ("payment_link_id", sa.Column("payment_link_id", sa.String(255), nullable=True)),
        (
            "payment_link_created_at",
            sa.Column("payment_link_created_at", sa.DateTime(), nullable=True),
        ),
    ]
    for name, column in new_invoice_columns:
        if name not in invoice_columns:
            op.add_column("invoices", column)

    # Speeds up the reminder sweep and the A/R aging report, both of which scan
    # open invoices by due date.
    existing_invoice_indexes = {
        idx["name"] for idx in sa.inspect(op.get_bind()).get_indexes("invoices")
    }
    if "idx_invoices_due_status_deleted" not in existing_invoice_indexes:
        op.create_index(
            "idx_invoices_due_status_deleted",
            "invoices",
            ["due_date", "status", "deleted_at"],
        )

    profile_columns = _existing_columns("business_profile")
    new_profile_columns = [
        (
            "reminders_enabled",
            sa.Column("reminders_enabled", sa.Integer(), nullable=False, server_default="0"),
        ),
        # JSON array of day offsets relative to due date, e.g. [-3, 1, 7, 14].
        ("reminder_offsets", sa.Column("reminder_offsets", sa.Text(), nullable=True)),
        (
            "reminder_subject_template",
            sa.Column("reminder_subject_template", sa.String(500), nullable=True),
        ),
        ("reminder_body_template", sa.Column("reminder_body_template", sa.Text(), nullable=True)),
        (
            "payments_enabled",
            sa.Column("payments_enabled", sa.Integer(), nullable=False, server_default="0"),
        ),
        ("payments_provider", sa.Column("payments_provider", sa.String(20), nullable=True)),
        # Encrypted at rest via invoice_machine.crypto (enc: prefix).
        ("stripe_secret_key", sa.Column("stripe_secret_key", sa.String(500), nullable=True)),
        (
            "stripe_webhook_secret",
            sa.Column("stripe_webhook_secret", sa.String(500), nullable=True),
        ),
        # JSON object of currency -> rate into default_currency_code.
        ("fx_rates", sa.Column("fx_rates", sa.Text(), nullable=True)),
    ]
    for name, column in new_profile_columns:
        if name not in profile_columns:
            op.add_column("business_profile", column)


def downgrade() -> None:
    for column in (
        "fx_rates",
        "stripe_webhook_secret",
        "stripe_secret_key",
        "payments_provider",
        "payments_enabled",
        "reminder_body_template",
        "reminder_subject_template",
        "reminder_offsets",
        "reminders_enabled",
    ):
        op.drop_column("business_profile", column)

    op.drop_index("idx_invoices_due_status_deleted", table_name="invoices")
    for column in (
        "payment_link_created_at",
        "payment_link_id",
        "payment_link_url",
        "last_reminder_sent_at",
        "reminders_sent",
        "converted_to_invoice_id",
        "converted_from_invoice_id",
        "base_currency_code",
        "exchange_rate",
        "amount_paid",
    ):
        op.drop_column("invoices", column)

    op.drop_index("idx_payments_provider_external", table_name="payments")
    op.drop_index("idx_payments_date", table_name="payments")
    op.drop_index("idx_payments_invoice", table_name="payments")
    op.drop_table("payments")
