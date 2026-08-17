"""Widen credential columns and enforce a single administrator row.

``hash_api_key`` stores ``hash:<32-hex-salt>:<64-hex-digest>`` (102 characters).
The columns were VARCHAR(64) from when keys were stored in plaintext. SQLite
does not enforce the declared width, so existing deployments still work, but
any engine that does would truncate the hash and make every key fail to verify.

An encrypted SMTP password (Fernet ciphertext plus the ``enc:`` prefix) of a
long password also exceeds VARCHAR(255).

Revision ID: 018_credential_widths
Revises: 017_payment_idempotency
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018_credential_widths"
down_revision: str | None = "017_payment_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("singleton", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.create_unique_constraint("uq_users_singleton", ["singleton"])

    with op.batch_alter_table("business_profile") as batch_op:
        batch_op.alter_column(
            "mcp_api_key",
            existing_type=sa.String(length=64),
            type_=sa.String(length=128),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "bot_api_key",
            existing_type=sa.String(length=64),
            type_=sa.String(length=128),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "smtp_password",
            existing_type=sa.String(length=255),
            type_=sa.String(length=500),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_singleton", type_="unique")
        batch_op.drop_column("singleton")

    with op.batch_alter_table("business_profile") as batch_op:
        batch_op.alter_column(
            "smtp_password",
            existing_type=sa.String(length=500),
            type_=sa.String(length=255),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "bot_api_key",
            existing_type=sa.String(length=128),
            type_=sa.String(length=64),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "mcp_api_key",
            existing_type=sa.String(length=128),
            type_=sa.String(length=64),
            existing_nullable=True,
        )
