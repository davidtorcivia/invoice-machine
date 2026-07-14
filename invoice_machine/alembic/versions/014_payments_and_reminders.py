"""Add optional payments, payment audit events, and reminder delivery state.

Revision ID: 014_payments_reminders
Revises: 013_quantity_decimal
Create Date: 2026-07-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014_payments_reminders"
down_revision: str | None = "013_quantity_decimal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("business_profile") as batch_op:
        batch_op.add_column(
            sa.Column("online_payments_enabled", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("payment_provider", sa.String(30), nullable=True))
        batch_op.add_column(sa.Column("stripe_secret_key", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("stripe_webhook_secret", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("reminders_enabled", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column(
                "reminder_offsets", sa.Text(), nullable=False, server_default="[-3, 0, 3, 7]"
            )
        )
        batch_op.add_column(sa.Column("reminder_subject_template", sa.String(500)))
        batch_op.add_column(sa.Column("reminder_body_template", sa.Text()))
        batch_op.add_column(
            sa.Column("business_timezone", sa.String(100), nullable=False, server_default="UTC")
        )
        batch_op.add_column(
            sa.Column("reminder_send_hour", sa.Integer(), nullable=False, server_default="9")
        )

    with op.batch_alter_table("invoices") as batch_op:
        batch_op.add_column(
            sa.Column("online_payment_enabled", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("payment_token", sa.String(96), nullable=True))
        batch_op.add_column(sa.Column("payment_checkout_provider", sa.String(30)))
        batch_op.add_column(sa.Column("payment_checkout_id", sa.String(255)))
        batch_op.add_column(sa.Column("payment_checkout_url", sa.Text()))
        batch_op.add_column(sa.Column("payment_checkout_amount", sa.Numeric(12, 2)))
        batch_op.add_column(sa.Column("payment_checkout_currency", sa.String(3)))
        batch_op.add_column(sa.Column("payment_checkout_idempotency_key", sa.String(255)))
        batch_op.add_column(sa.Column("payment_checkout_fingerprint", sa.String(64)))
        batch_op.add_column(sa.Column("payment_checkout_expires_at", sa.DateTime()))
        batch_op.add_column(
            sa.Column("reminders_enabled", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.create_unique_constraint("uq_invoices_payment_token", ["payment_token"])

    with op.batch_alter_table("recurring_schedules") as batch_op:
        batch_op.add_column(sa.Column("auto_send", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(
            sa.Column("reminders_enabled", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(
            sa.Column("online_payment_enabled", sa.Integer(), nullable=False, server_default="0")
        )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "invoice_id",
            sa.Integer(),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("refunded_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("disputed_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("dispute_status", sa.String(20), nullable=True),
        sa.Column("fee_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(30), nullable=False, server_default="succeeded"),
        sa.Column("provider_payment_id", sa.String(255), nullable=True),
        sa.Column("provider_checkout_id", sa.String(255), nullable=True),
        sa.Column("provider_charge_id", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "provider", "provider_payment_id", name="uq_payments_provider_payment"
        ),
        sa.UniqueConstraint(
            "provider", "provider_checkout_id", name="uq_payments_provider_checkout"
        ),
    )
    op.create_index("idx_payments_invoice", "payments", ["invoice_id"])
    op.create_index("idx_payments_status", "payments", ["status"])

    op.create_table(
        "payment_refunds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "payment_id",
            sa.Integer(),
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_payment_refunds_provider_event"
        ),
    )
    op.create_index("idx_payment_refunds_payment", "payment_refunds", ["payment_id"])
    op.create_index("idx_payment_refunds_occurred", "payment_refunds", ["occurred_at"])

    op.create_table(
        "payment_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "payment_id",
            sa.Integer(),
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name="uq_payment_adjustments_provider_event"
        ),
    )
    op.create_index("idx_payment_adjustments_payment", "payment_adjustments", ["payment_id"])
    op.create_index("idx_payment_adjustments_occurred", "payment_adjustments", ["occurred_at"])

    op.create_table(
        "provider_refund_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "payment_id",
            sa.Integer(),
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provider_refund_id", sa.String(255), nullable=True),
        sa.Column("provider_refund_status", sa.String(30), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "provider", "idempotency_key", name="uq_provider_refund_requests_key"
        ),
    )
    op.create_index(
        "idx_provider_refund_requests_payment", "provider_refund_requests", ["payment_id"]
    )

    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="processed"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("provider", "event_id", name="uq_payment_events_provider_event"),
    )
    op.create_index("idx_payment_events_processed", "payment_events", ["processed_at"])

    op.create_table(
        "reminder_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "invoice_id",
            sa.Integer(),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("offset_days", sa.Integer(), nullable=False),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "invoice_id", "due_date", "offset_days", name="uq_reminder_invoice_due_offset"
        ),
    )
    op.create_index("idx_reminders_invoice", "reminder_deliveries", ["invoice_id"])
    op.create_index("idx_reminders_status", "reminder_deliveries", ["status"])

    # Existing manually-paid invoices retain their cash history and immediately
    # participate in the new ledger-based analytics.
    op.execute(
        """
        INSERT INTO payments (
            invoice_id, amount, refunded_amount, currency_code, provider, status,
            notes, occurred_at, created_at, updated_at
        )
        SELECT id, total, 0, currency_code, 'manual', 'succeeded',
               'Migrated from legacy paid status',
               COALESCE(paid_at, updated_at, created_at),
               COALESCE(paid_at, updated_at, created_at),
               COALESCE(paid_at, updated_at, created_at)
        FROM invoices
        WHERE status = 'paid' AND total > 0
        """
    )


def downgrade() -> None:
    op.drop_index("idx_reminders_status", table_name="reminder_deliveries")
    op.drop_index("idx_reminders_invoice", table_name="reminder_deliveries")
    op.drop_table("reminder_deliveries")
    op.drop_index(
        "idx_provider_refund_requests_payment", table_name="provider_refund_requests"
    )
    op.drop_table("provider_refund_requests")
    op.drop_index("idx_payment_adjustments_occurred", table_name="payment_adjustments")
    op.drop_index("idx_payment_adjustments_payment", table_name="payment_adjustments")
    op.drop_table("payment_adjustments")
    op.drop_index("idx_payment_events_processed", table_name="payment_events")
    op.drop_table("payment_events")
    op.drop_index("idx_payment_refunds_occurred", table_name="payment_refunds")
    op.drop_index("idx_payment_refunds_payment", table_name="payment_refunds")
    op.drop_table("payment_refunds")
    op.drop_index("idx_payments_status", table_name="payments")
    op.drop_index("idx_payments_invoice", table_name="payments")
    op.drop_table("payments")

    with op.batch_alter_table("recurring_schedules") as batch_op:
        batch_op.drop_column("online_payment_enabled")
        batch_op.drop_column("reminders_enabled")
        batch_op.drop_column("auto_send")
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.drop_constraint("uq_invoices_payment_token", type_="unique")
        batch_op.drop_column("reminders_enabled")
        batch_op.drop_column("payment_checkout_expires_at")
        batch_op.drop_column("payment_checkout_fingerprint")
        batch_op.drop_column("payment_checkout_idempotency_key")
        batch_op.drop_column("payment_checkout_currency")
        batch_op.drop_column("payment_checkout_amount")
        batch_op.drop_column("payment_checkout_url")
        batch_op.drop_column("payment_checkout_id")
        batch_op.drop_column("payment_checkout_provider")
        batch_op.drop_column("payment_token")
        batch_op.drop_column("online_payment_enabled")
    with op.batch_alter_table("business_profile") as batch_op:
        batch_op.drop_column("reminder_send_hour")
        batch_op.drop_column("business_timezone")
        batch_op.drop_column("reminder_body_template")
        batch_op.drop_column("reminder_subject_template")
        batch_op.drop_column("reminder_offsets")
        batch_op.drop_column("reminders_enabled")
        batch_op.drop_column("stripe_webhook_secret")
        batch_op.drop_column("stripe_secret_key")
        batch_op.drop_column("payment_provider")
        batch_op.drop_column("online_payments_enabled")
