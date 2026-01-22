"""Add sessions table for database-backed session management.

Replaces in-memory session storage with persistent database sessions for:
- Multi-instance scalability
- Session persistence across restarts
- CSRF protection via per-session tokens
- Session audit trail (IP, user agent)

Revision ID: 010_add_sessions
Revises: 009_recurring_enhancements
Create Date: 2026-01-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "010_add_sessions"
down_revision: Union[str, None] = "009_recurring_enhancements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Get existing tables to make migration idempotent
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "sessions" not in existing_tables:
        op.create_table(
            "sessions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("token", sa.String(64), nullable=False, unique=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("csrf_token", sa.String(64), nullable=False),
            # Session metadata for security auditing
            sa.Column("user_agent", sa.String(500), nullable=True),
            sa.Column("ip_address", sa.String(45), nullable=True),  # IPv6 max length
        )
        # Index on token for fast lookups (also unique constraint)
        op.create_index("idx_sessions_token", "sessions", ["token"], unique=True)
        # Index on expires_at for efficient cleanup of expired sessions
        op.create_index("idx_sessions_expires", "sessions", ["expires_at"])
        # Index on user_id for finding all sessions for a user
        op.create_index("idx_sessions_user", "sessions", ["user_id"])


def downgrade() -> None:
    op.drop_table("sessions")
