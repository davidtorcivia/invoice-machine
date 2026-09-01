"""Database models and connection management."""

import hashlib
from collections.abc import AsyncIterator
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional, cast

from sqlalchemy import (
    DECIMAL,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

from invoice_machine.config import get_settings
from invoice_machine.utils import ensure_utc, utc_now


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class User(Base):
    """User account for authentication."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    # Always 1. Unique so two concurrent /setup POSTs cannot both succeed.
    singleton: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", unique=True, nullable=False
    )

    @classmethod
    async def get_by_username(cls, session: "AsyncSession", username: str) -> Optional["User"]:
        """Get user by username (case-insensitive)."""
        from sqlalchemy import func, select

        result = await session.execute(
            select(cls).where(func.lower(cls.username) == username.lower())
        )
        return result.scalar_one_or_none()

    @classmethod
    async def count(cls, session: "AsyncSession") -> int:
        """Count total users."""
        from sqlalchemy import func, select

        result = await session.execute(select(func.count(cls.id)))
        return result.scalar() or 0


class BusinessProfile(Base):
    """User's business profile (singleton - only one record, id=1)."""

    __tablename__ = "business_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_line2: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="United States")
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ein: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Tax ID
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    accent_color: Mapped[str] = mapped_column(String(7), default="#16a34a")
    default_payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    default_currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    default_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_payment_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON array: [{id, name, instructions}]
    payment_methods: Mapped[str | None] = mapped_column(Text, nullable=True)
    theme_preference: Mapped[str] = mapped_column(String(20), default="system")
    app_base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    backup_enabled: Mapped[int] = mapped_column(Integer, default=1)  # Daily auto-backup
    backup_retention_days: Mapped[int] = mapped_column(Integer, default=30)
    backup_s3_enabled: Mapped[int] = mapped_column(Integer, default=0)
    # JSON: {endpoint_url, access_key_id, secret_access_key, bucket, region, prefix}
    backup_s3_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_tax_enabled: Mapped[int] = mapped_column(Integer, default=0)
    default_tax_rate: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), default=Decimal("0.00"))
    default_tax_name: Mapped[str] = mapped_column(String(50), default="Tax")
    smtp_enabled: Mapped[int] = mapped_column(Integer, default=0)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Fernet ciphertext of a long password plus the enc: prefix exceeds 255.
    smtp_password: Mapped[str | None] = mapped_column(String(500), nullable=True)
    smtp_from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_use_tls: Mapped[int] = mapped_column(Integer, default=1)
    email_subject_template: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email_body_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    # IANA timezone the business operates in. Reminder timing and "days until
    # due" are computed against this, not UTC.
    business_timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    reminders_enabled: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Local hour (0-23) at which the daily reminder sweep runs.
    reminder_send_hour: Mapped[int] = mapped_column(Integer, default=9, server_default="9")
    # JSON array of day offsets relative to due date (negative = before due).
    reminder_offsets: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminder_subject_template: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reminder_body_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    payments_enabled: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    payments_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Both encrypted at rest (enc: prefix) via invoice_machine.crypto.
    stripe_secret_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stripe_webhook_secret: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # JSON object of currency code -> rate into default_currency_code.
    fx_rates: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    @classmethod
    async def get(cls, session: AsyncSession) -> Optional["BusinessProfile"]:
        """Get the singleton business profile."""
        from sqlalchemy import select

        result = await session.execute(select(cls).where(cls.id == 1))
        return result.scalar_one_or_none()

    @classmethod
    async def get_or_create(cls, session: AsyncSession) -> "BusinessProfile":
        """Get existing profile or create default."""
        profile = await cls.get(session)
        if profile is None:
            profile = cls(id=1, name="Your Name")
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
        return profile

    @property
    def payment_methods_list(self) -> list[dict]:
        """Parse configured payment methods from stored JSON."""
        import json

        if not self.payment_methods:
            return []
        try:
            methods = json.loads(self.payment_methods)
            return methods if isinstance(methods, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def reminder_offsets_list(self) -> list[int]:
        """Reminder day-offsets relative to due date, sorted and de-duplicated."""
        import json

        if not self.reminder_offsets:
            return []
        try:
            offsets = json.loads(self.reminder_offsets)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(offsets, list):
            return []
        return sorted({int(o) for o in offsets if isinstance(o, (int, float))})

    @property
    def fx_rates_map(self) -> dict[str, Decimal]:
        """Currency -> rate into default_currency_code. Bad entries are dropped."""
        import json
        from decimal import InvalidOperation

        if not self.fx_rates:
            return {}
        try:
            raw = json.loads(self.fx_rates)
        except (json.JSONDecodeError, TypeError):
            return {}
        if not isinstance(raw, dict):
            return {}

        rates: dict[str, Decimal] = {}
        for code, value in raw.items():
            try:
                rate = Decimal(str(value))
            except (InvalidOperation, ValueError, TypeError):
                continue
            if rate.is_finite() and rate > 0:
                rates[str(code).upper()] = rate
        return rates


class ApiKey(Base):
    """A labeled, individually revocable API key (kind "mcp" or "bot")."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    # Stored as hash:<salt>:<sha256> (~102 chars); see crypto.hash_api_key.
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    # First 12 characters of the plain key, for display. NULL for keys migrated
    # from the old single-key columns, whose plaintext was never stored.
    prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("idx_api_keys_kind", "kind"),)


class Client(Base):
    """Client (customer/company)."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Contact name
    business_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Company
    address_line1: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_line2: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Per-client tax settings (None = use global default, explicit value = override)
    tax_enabled: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_rate: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2), nullable=True)
    tax_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Per-client currency preference (None = use global default)
    preferred_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    invoices: Mapped[list["Invoice"]] = relationship(
        "Invoice",
        back_populates="client",
        foreign_keys="Invoice.client_id",
        # No code reads client.invoices; the back-reference exists only for the
        # Invoice.client side. "raise" turns an accidental eager full-table load
        # into a loud error instead of a silent N+1.
        lazy="raise",
    )

    __table_args__ = (
        Index("idx_clients_deleted", "deleted_at"),
        Index("idx_clients_email", "email"),
        Index("idx_clients_name", "name"),
        Index("idx_clients_business_name", "business_name"),
    )

    @property
    def display_name(self) -> str:
        """Get a display name (business name or contact name)."""
        return self.business_name or self.name or "Unknown Client"

    @property
    def is_active(self) -> bool:
        """Check if client is active (not deleted)."""
        return self.deleted_at is None


class Invoice(Base):
    """Invoice with line items."""

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    client_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("clients.id"), nullable=True)

    # Denormalized client snapshot
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_business: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="draft")
    # Timestamp set when the invoice transitions to "paid" (cleared if un-paid).
    # Used for cash-basis reporting ("paid this month") instead of created_at.
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Sum of recorded payments, denormalized from the payments table so list and
    # aging queries never have to aggregate per row.
    amount_paid: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 2), default=Decimal("0.00"), server_default="0"
    )
    document_type: Mapped[str] = mapped_column(String(20), default="invoice")  # invoice/quote
    client_reference: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # PO/job number
    show_payment_instructions: Mapped[int] = mapped_column(Integer, default=1)
    # JSON array of payment method IDs selected for this invoice
    selected_payment_methods: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    subtotal: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=0)
    # Snapshot of the applicable tax settings at invoice creation time.
    tax_enabled: Mapped[int] = mapped_column(Integer, default=0)
    tax_rate: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), default=Decimal("0.00"))
    tax_name: Mapped[str] = mapped_column(String(50), default="Tax")
    tax_amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Rate to convert this invoice's currency into base_currency_code, captured at
    # issue time. NULL means "not recorded" — consolidated reporting excludes those
    # invoices and says so rather than guessing a rate.
    exchange_rate: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 8), nullable=True)
    base_currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)

    # Quote <-> invoice conversion links. Plain integers, not declared foreign
    # keys: SQLite cannot add a FK constraint to an existing table via ALTER
    # TABLE, so a declared FK here would make the create_all schema diverge from
    # the migrated one.
    converted_from_invoice_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    converted_to_invoice_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Reminder bookkeeping: JSON array of day-offsets already sent, so a restart
    # or a second run on the same day cannot re-send the same reminder.
    reminders_sent: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Hosted payment link (Stripe Checkout Session) for this invoice.
    payment_link_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payment_link_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_link_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    client: Mapped[Optional["Client"]] = relationship(
        "Client",
        back_populates="invoices",
        foreign_keys=[client_id],
        lazy="selectin",
    )
    items: Mapped[list["InvoiceItem"]] = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItem.sort_order",
        lazy="selectin",
    )

    payments: Mapped[list["Payment"]] = relationship(
        "Payment",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="Payment.payment_date",
        # The balance lives in the denormalized amount_paid and PaymentService
        # queries this table directly, so "raise" keeps eager loading from adding
        # a second query to every invoice list.
        lazy="raise",
    )

    __table_args__ = (
        Index("idx_invoices_date", "issue_date"),
        Index("idx_invoices_status", "status"),
        Index("idx_invoices_client", "client_id"),
        Index("idx_invoices_deleted", "deleted_at"),
        Index("idx_invoices_status_deleted", "status", "deleted_at"),
        Index("idx_invoices_client_status", "client_id", "status"),
        Index("idx_invoices_date_status", "issue_date", "status"),
        Index(
            "uq_invoices_converted_from",
            "converted_from_invoice_id",
            unique=True,
        ),
        Index("idx_invoices_client_deleted", "client_id", "deleted_at"),
        # Reminder sweep and A/R aging both scan open invoices by due date.
        Index("idx_invoices_due_status_deleted", "due_date", "status", "deleted_at"),
    )

    @property
    def is_active(self) -> bool:
        """Check if invoice is active (not deleted)."""
        return self.deleted_at is None

    @property
    def amount_due(self) -> Decimal:
        """Outstanding balance (never negative, so an overpayment reads as 0 due)."""
        total = Decimal(str(self.total or 0))
        paid = Decimal(str(self.amount_paid or 0))
        return max(total - paid, Decimal("0.00"))

    @property
    def is_partially_paid(self) -> bool:
        """True when some — but not all — of the invoice has been paid.

        Deliberately derived rather than a new `status` value: adding a status
        would ripple through every filter, badge, bulk action and analytics
        bucket, while the money question is fully answered by amount_paid.
        """
        paid = Decimal(str(self.amount_paid or 0))
        return paid > 0 and paid < Decimal(str(self.total or 0))

    @property
    def reminders_sent_list(self) -> list[int]:
        """Day-offsets whose reminder has already been sent for this invoice."""
        import json

        if not self.reminders_sent:
            return []
        try:
            offsets = json.loads(self.reminders_sent)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(offsets, list):
            return []
        return [int(offset) for offset in offsets if isinstance(offset, (int, float))]

    @property
    def needs_pdf_regeneration(self) -> bool:
        """Check if PDF needs regeneration."""
        if self.pdf_generated_at is None:
            return True
        updated_at = ensure_utc(self.updated_at)
        pdf_generated_at = ensure_utc(self.pdf_generated_at)
        return bool(updated_at and pdf_generated_at and updated_at > pdf_generated_at)

    @property
    def selected_payment_methods_list(self) -> list[str]:
        """Parse selected payment method IDs from stored JSON."""
        import json

        if not self.selected_payment_methods:
            return []
        try:
            methods = json.loads(self.selected_payment_methods)
            return methods if isinstance(methods, list) else []
        except (json.JSONDecodeError, TypeError):
            return []


class InvoiceItem(Base):
    """Line item for an invoice."""

    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Decimal so fractional hours (1.5, 0.25) can be billed.
    quantity: Mapped[Decimal] = mapped_column(DECIMAL(12, 3), default=Decimal("1"))
    unit_type: Mapped[str] = mapped_column(String(10), default="qty")  # qty/hours
    unit_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="items", lazy="selectin")

    __table_args__ = (Index("idx_items_invoice", "invoice_id"),)


class Payment(Base):
    """A payment recorded against an invoice.

    Multiple payments per invoice give partial-payment support; the invoice's
    denormalized ``amount_paid`` is recomputed from this table on every change.
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    # Snapshot of the invoice currency at payment time: money is never summed
    # across currencies, and a later currency edit must not relabel history.
    currency_code: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set only for payments created by a provider webhook (e.g. "stripe").
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Caller-supplied replay guard for manually recorded payments. NULL for
    # payments recorded before keys existed, and NULLs do not collide.
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="payments")

    __table_args__ = (
        Index("idx_payments_invoice", "invoice_id"),
        Index("idx_payments_date", "payment_date"),
        # Webhook idempotency: one provider event can only ever land once.
        Index("idx_payments_provider_external", "provider", "external_id", unique=True),
        # Caller idempotency, on the key alone: keys are only set on the manual
        # path (provider NULL), and a unique index treats NULLs as distinct, so a
        # (provider, idempotency_key) index would enforce nothing.
        Index("uq_payments_idempotency_key", "idempotency_key", unique=True),
    )


def _digest_session_token(token: str) -> str:
    """SHA-256 hex of a session cookie. Fits the existing VARCHAR(64) column."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _looks_like_session_digest(token: str) -> bool:
    """True for a stored digest. token_urlsafe cookies use base64 and almost never match."""
    return len(token) == 64 and all(c in "0123456789abcdef" for c in token)


class Session(Base):
    """Database-backed user session."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # unique=True already creates an index for token lookups; no separate index.
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max length

    user: Mapped["User"] = relationship("User", lazy="selectin")

    if TYPE_CHECKING:
        # Set by create() to carry the plaintext cookie value to the caller.
        # Deliberately unmapped: only the digest is ever persisted.
        cookie_token: str

    __table_args__ = (
        Index("idx_sessions_expires", "expires_at"),
        Index("idx_sessions_user", "user_id"),
    )

    @classmethod
    async def create(
        cls,
        session: "AsyncSession",
        user_id: int,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> "Session":
        """Create a new session."""
        import secrets

        plain = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(48)

        db_session = cls(
            token=_digest_session_token(plain),
            user_id=user_id,
            expires_at=expires_at,
            csrf_token=csrf_token,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        session.add(db_session)
        await session.commit()
        await session.refresh(db_session)
        # Cookie still carries the plaintext; only the digest is stored.
        db_session.cookie_token = plain
        return db_session

    @classmethod
    async def get_by_token(cls, session: "AsyncSession", token: str) -> Optional["Session"]:
        """Get session by cookie token if valid and not expired."""
        from sqlalchemy import select

        digest = _digest_session_token(token)
        result = await session.execute(
            select(cls).where(cls.token == digest, cls.expires_at > utc_now())
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row

        # Leftover plaintext row from before tokens were hashed.
        # Skip when the cookie is already 64 hex: that is a stolen digest,
        # not a pre-hash cookie (token_urlsafe uses base64).
        if _looks_like_session_digest(token):
            return None
        result = await session.execute(
            select(cls).where(cls.token == token, cls.expires_at > utc_now())
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.token = digest
        await session.commit()
        return row

    @classmethod
    async def delete_by_token(cls, session: "AsyncSession", token: str) -> bool:
        """Delete a session by cookie token (digest or leftover plaintext)."""
        from sqlalchemy import delete

        digest = _digest_session_token(token)
        result = cast(
            CursorResult[Any],
            await session.execute(delete(cls).where(cls.token.in_((digest, token)))),
        )
        await session.commit()
        return result.rowcount > 0

    @classmethod
    async def delete_expired(cls, session: "AsyncSession") -> int:
        """Delete all expired sessions. Returns count of deleted sessions."""
        from sqlalchemy import delete

        result = cast(
            CursorResult[Any], await session.execute(delete(cls).where(cls.expires_at <= utc_now()))
        )
        await session.commit()
        return result.rowcount

    @classmethod
    async def delete_user_sessions(cls, session: "AsyncSession", user_id: int) -> int:
        """Delete all sessions for a user (logout everywhere)."""
        from sqlalchemy import delete

        result = cast(
            CursorResult[Any], await session.execute(delete(cls).where(cls.user_id == user_id))
        )
        await session.commit()
        return result.rowcount

    @classmethod
    async def delete_other_sessions(
        cls, session: "AsyncSession", user_id: int, keep_token: str
    ) -> int:
        """Delete every session for a user except the one that just authenticated."""
        from sqlalchemy import delete

        digest = _digest_session_token(keep_token)
        result = cast(
            CursorResult[Any],
            await session.execute(
                delete(cls).where(
                    cls.user_id == user_id,
                    cls.token.notin_((digest, keep_token)),
                )
            ),
        )
        await session.commit()
        return result.rowcount


class RecurringSchedule(Base):
    """Recurring invoice schedule."""

    __tablename__ = "recurring_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Frequency: daily, weekly, monthly, quarterly, yearly
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    # Day of month (1-31) for monthly/quarterly/yearly, or day of week (0-6) for weekly
    schedule_day: Mapped[int] = mapped_column(Integer, default=1)
    # Calendar month (1-12) for yearly schedules. None = keep the created month.
    schedule_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Which month within each quarter (1-3) for quarterly schedules.
    quarter_month: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When set, generated invoices inherit the business profile's default notes
    # instead of this schedule's own notes.
    use_default_notes: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # JSON array of line items: [{description, quantity, unit_price, unit_type}]
    line_items: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Payment-instruction settings copied onto each generated invoice.
    show_payment_instructions: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # JSON array of payment method IDs
    selected_payment_methods: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Email each generated invoice to the client automatically.
    auto_email_enabled: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    email_subject_template: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email_body_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Tax settings (inherit from client/global if not set)
    tax_enabled: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_rate: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 2), nullable=True)
    tax_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    next_invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_invoice_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("invoices.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    client: Mapped["Client"] = relationship("Client", lazy="selectin")
    last_invoice: Mapped[Optional["Invoice"]] = relationship(
        "Invoice", foreign_keys=[last_invoice_id], lazy="selectin"
    )

    __table_args__ = (
        Index("idx_recurring_client", "client_id"),
        Index("idx_recurring_next_date", "next_invoice_date"),
        Index("idx_recurring_active", "is_active"),
        Index("idx_recurring_active_next_date", "is_active", "next_invoice_date"),
    )

    @property
    def line_items_list(self) -> list[dict]:
        """Parse recurring schedule line items from stored JSON."""
        import json

        if not self.line_items:
            return []
        try:
            items = json.loads(self.line_items)
            return items if isinstance(items, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def selected_payment_methods_list(self) -> list[str]:
        """Parse selected payment method IDs from stored JSON."""
        import json

        if not self.selected_payment_methods:
            return []
        try:
            methods = json.loads(self.selected_payment_methods)
            return methods if isinstance(methods, list) else []
        except (json.JSONDecodeError, TypeError):
            return []


settings = get_settings()

db_url = settings.database_url
if db_url.startswith("sqlite://"):
    db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)


def _apply_sqlite_pragmas(dbapi_connection) -> None:
    """Apply required PRAGMAs to a raw SQLite DBAPI connection.

    SQLite needs these set per-connection:
    - foreign_keys=ON   -> enforce FK constraints / ON DELETE CASCADE
    - journal_mode=WAL  -> concurrent readers during writes, safer backups
    - busy_timeout      -> wait instead of immediately raising "database is locked"
    - synchronous=NORMAL-> safe with WAL, much faster than FULL
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def register_sqlite_pragmas(target_engine) -> None:
    """Register a connect-time PRAGMA listener on a sync or async SQLite engine."""
    sync_engine = getattr(target_engine, "sync_engine", target_engine)
    if sync_engine.dialect.name != "sqlite":
        return

    @event.listens_for(sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ARG001
        _apply_sqlite_pragmas(dbapi_connection)


engine = create_async_engine(
    db_url,
    echo=False,
    pool_pre_ping=True,  # Verify connections before use
    connect_args={"check_same_thread": False},  # Allow multi-threaded access
)
register_sqlite_pragmas(engine)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Get async database session."""
    async with async_session_maker() as session:
        yield session


async def init_db():
    """Initialize database schema."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connections."""
    await engine.dispose()
