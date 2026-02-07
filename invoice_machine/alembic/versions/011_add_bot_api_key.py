"""Add dedicated bot API key column to business_profile.

Revision ID: 011_add_bot_api_key
Revises: 010_add_sessions
Create Date: 2026-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "011_add_bot_api_key"
down_revision: Union[str, None] = "010_add_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("business_profile")}

    if "bot_api_key" not in columns:
        op.add_column(
            "business_profile",
            sa.Column("bot_api_key", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("business_profile")}

    if "bot_api_key" in columns:
        op.drop_column("business_profile", "bot_api_key")
