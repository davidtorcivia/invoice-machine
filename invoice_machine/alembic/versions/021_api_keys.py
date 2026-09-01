"""Replace the single MCP/bot key columns with labeled, revocable API keys.

Each existing key becomes one row in ``api_keys`` so live integrations keep
working; their plaintext was never stored, so the display prefix is NULL.

Downgrading is lossy: the old schema holds one key per kind, so only the newest
hashed key of each kind is copied back and the rest are dropped.

Revision ID: 021_api_keys
Revises: 020_backfill_marked_paid
Create Date: 2026-09-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021_api_keys"
down_revision: str | None = "020_backfill_marked_paid"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MIGRATED_LABELS = {"mcp": "Migrated MCP key", "bot": "Migrated bot key"}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "api_keys" not in inspector.get_table_names():
        op.create_table(
            "api_keys",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("kind", sa.String(8), nullable=False),
            sa.Column("label", sa.String(100), nullable=False),
            sa.Column("key_hash", sa.String(128), nullable=False),
            sa.Column("prefix", sa.String(16), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
        )
        op.create_index("idx_api_keys_kind", "api_keys", ["kind"])

    columns = {col["name"] for col in inspector.get_columns("business_profile")}
    present = [kind for kind in ("mcp", "bot") if f"{kind}_api_key" in columns]

    for kind in present:
        rows = conn.execute(
            sa.text(
                f"SELECT {kind}_api_key AS key FROM business_profile "
                f"WHERE {kind}_api_key IS NOT NULL AND {kind}_api_key != ''"
            )
        ).fetchall()
        for row in rows:
            conn.execute(
                sa.text(
                    "INSERT INTO api_keys (kind, label, key_hash, prefix, created_at) "
                    "VALUES (:kind, :label, :key_hash, NULL, CURRENT_TIMESTAMP)"
                ),
                {"kind": kind, "label": MIGRATED_LABELS[kind], "key_hash": row.key},
            )

    if present:
        with op.batch_alter_table("business_profile") as batch_op:
            for kind in present:
                batch_op.drop_column(f"{kind}_api_key")


def downgrade() -> None:
    conn = op.get_bind()

    with op.batch_alter_table("business_profile") as batch_op:
        batch_op.add_column(sa.Column("mcp_api_key", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("bot_api_key", sa.String(128), nullable=True))

    for kind in ("mcp", "bot"):
        row = conn.execute(
            sa.text(
                "SELECT key_hash FROM api_keys WHERE kind = :kind AND key_hash LIKE 'hash:%' "
                "ORDER BY created_at DESC, id DESC LIMIT 1"
            ),
            {"kind": kind},
        ).fetchone()
        if row:
            conn.execute(
                sa.text(f"UPDATE business_profile SET {kind}_api_key = :key"),
                {"key": row.key_hash},
            )

    op.drop_index("idx_api_keys_kind", table_name="api_keys")
    op.drop_table("api_keys")
