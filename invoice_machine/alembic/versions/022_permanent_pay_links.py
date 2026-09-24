"""Permanent pay links: invoices.payment_link_id holds the /pay/<token> token.

Links used to be Stripe Checkout Session URLs, which Stripe expires within 24
hours. Each existing one becomes a /pay/<token> link on this app's base URL, and
its cached PDF is marked stale so the reprint carries the working link.

Revision ID: 022_permanent_pay_links
Revises: 021_api_keys
Create Date: 2026-09-24

"""

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from invoice_machine.config import get_settings

revision: str = "022_permanent_pay_links"
down_revision: str | None = "021_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    profile_base = conn.execute(
        sa.text("SELECT app_base_url FROM business_profile WHERE id = 1")
    ).scalar()
    base_url = (profile_base or get_settings().app_base_url or "").rstrip("/")

    rows = conn.execute(
        sa.text("SELECT id FROM invoices WHERE payment_link_id LIKE 'cs\\_%' ESCAPE '\\'")
    ).fetchall()
    for row in rows:
        if base_url.startswith(("https://", "http://")):
            token = secrets.token_urlsafe(24)
            values = {"token": token, "url": f"{base_url}/pay/{token}"}
        else:
            values = {"token": None, "url": None}
        conn.execute(
            sa.text(
                "UPDATE invoices SET payment_link_id = :token, payment_link_url = :url, "
                "pdf_generated_at = NULL WHERE id = :id"
            ),
            {**values, "id": row.id},
        )

    op.create_index("uq_invoices_payment_link_id", "invoices", ["payment_link_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_invoices_payment_link_id", table_name="invoices")
