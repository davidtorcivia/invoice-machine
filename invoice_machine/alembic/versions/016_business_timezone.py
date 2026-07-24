"""Add business timezone and reminder send hour.

Reminders previously ran at a fixed 09:00 UTC and computed "days until due" from
the UTC date. For anyone outside UTC that sends mail at the wrong local hour
(02:00 for US Pacific) and can misjudge the day by one near midnight.

Revision ID: 016_business_timezone
Revises: 015_backfill_paid
Create Date: 2026-07-24

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "016_business_timezone"
down_revision: str | None = "015_backfill_paid"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {
        col["name"] for col in sa.inspect(op.get_bind()).get_columns("business_profile")
    }
    if "business_timezone" not in columns:
        op.add_column(
            "business_profile",
            sa.Column(
                "business_timezone",
                sa.String(64),
                nullable=False,
                server_default="UTC",
            ),
        )
    if "reminder_send_hour" not in columns:
        op.add_column(
            "business_profile",
            sa.Column(
                "reminder_send_hour", sa.Integer(), nullable=False, server_default="9"
            ),
        )


def downgrade() -> None:
    op.drop_column("business_profile", "reminder_send_hour")
    op.drop_column("business_profile", "business_timezone")
