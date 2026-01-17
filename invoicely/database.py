"""Database models and connection management."""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    Text,
    DECIMAL,
    DateTime,
    Date,
    ForeignKey,
    CheckConstraint,
    Index,
    UniqueConstraint,
)
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

from invoicely.config import get_settings


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class User(Base):
    """User account for authentication."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @classmethod
    async def get_by_username(cls, session: "AsyncSession", username: str) -> Optional["User"]:
        """Get user by username (case-insensitive)."""
        from sqlalchemy import select, func
        result = await session.execute(
            select(cls).where(func.lower(cls.username) == username.lower())
        )
        return result.scalar_one_or_none()

    @classmethod
    async def count(cls, session: "AsyncSession") -> int:
        """Count total users."""
        from sqlalchemy import select, func
        result = await session.execute(select(func.count(cls.id)))
        return result.scalar() or 0


class BusinessProfile(Base):
    """User's business profile (singleton - only one record, id=1)."""

    __tablename__ = "business_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="United States")
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ein: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Tax ID
    logo_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    accent_color: Mapped[str] = mapped_column(String(7), default="#16a34a")
    default_payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    default_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_payment_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON array: [{id, name, instructions}]
    payment_methods: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    theme_preference: Mapped[str] = mapped_column(String(20), default="system")
    # MCP API key for remote access
    mcp_api_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # App base URL for links and MCP configuration
    app_base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Backup settings
    backup_enabled: Mapped[int] = mapped_column(Integer, default=1)  # Daily auto-backup
    backup_retention_days: Mapped[int] = mapped_column(Integer, default=30)
    backup_s3_enabled: Mapped[int] = mapped_column(Integer, default=0)
    # JSON: {endpoint_url, access_key_id, secret_access_key, bucket, region, prefix}
    backup_s3_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Tax settings (optional - disabled by default)
    default_tax_enabled: Mapped[int] = mapped_column(Integer, default=0)
    default_tax_rate: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), default=Decimal("0.00"))
    default_tax_name: Mapped[str] = mapped_column(String(50), default="Tax")
    # SMTP settings (optional - user must configure to enable email)
    smtp_enabled: Mapped[int] = mapped_column(Integer, default=0)
    smtp_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_from_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_from_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_use_tls: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

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


class Client(Base):
    """Client (customer/company)."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Contact name
    business_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )  # Company
    address_line1: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Per-client tax settings (None = use global default, explicit value = override)
    tax_enabled: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tax_rate: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 2), nullable=True)
    tax_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    invoices: Mapped[list["Invoice"]] = relationship(
        "Invoice",
        back_populates="client",
        foreign_keys="Invoice.client_id",
        lazy="selectin",
    )

    __table_args__ = (Index("idx_clients_deleted", "deleted_at"),)

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
    client_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=True
    )

    # Denormalized client snapshot
    client_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_business: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    client_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="draft")
    document_type: Mapped[str] = mapped_column(String(20), default="invoice")  # invoice/quote
    client_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # PO/job number
    show_payment_instructions: Mapped[int] = mapped_column(Integer, default=1)
    # JSON array of payment method IDs selected for this invoice
    selected_payment_methods: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    subtotal: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=0)
    # Tax fields (optional - snapshot at invoice creation time)
    tax_enabled: Mapped[int] = mapped_column(Integer, default=0)
    tax_rate: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), default=Decimal("0.00"))
    tax_name: Mapped[str] = mapped_column(String(50), default="Tax")
    tax_amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    pdf_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    pdf_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

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

    __table_args__ = (
        Index("idx_invoices_date", "issue_date"),
        Index("idx_invoices_status", "status"),
        Index("idx_invoices_client", "client_id"),
        Index("idx_invoices_deleted", "deleted_at"),
    )

    @property
    def is_active(self) -> bool:
        """Check if invoice is active (not deleted)."""
        return self.deleted_at is None

    @property
    def needs_pdf_regeneration(self) -> bool:
        """Check if PDF needs regeneration."""
        if self.pdf_generated_at is None:
            return True
        return self.updated_at > self.pdf_generated_at


class InvoiceItem(Base):
    """Line item for an invoice."""

    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_type: Mapped[str] = mapped_column(String(10), default="qty")  # qty/hours
    unit_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    invoice: Mapped["Invoice"] = relationship(
        "Invoice", back_populates="items", lazy="selectin"
    )

    __table_args__ = (Index("idx_items_invoice", "invoice_id"),)


class RecurringSchedule(Base):
    """Recurring invoice schedule."""

    __tablename__ = "recurring_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False
    )
    # Schedule name/description
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Frequency: daily, weekly, monthly, quarterly, yearly
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    # Day of month (1-31) for monthly/quarterly/yearly, or day of week (0-6) for weekly
    schedule_day: Mapped[int] = mapped_column(Integer, default=1)
    # Invoice template fields
    currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON array of line items: [{description, quantity, unit_price, unit_type}]
    line_items: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Tax settings (inherit from client/global if not set)
    tax_enabled: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tax_rate: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 2), nullable=True)
    tax_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Schedule status
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    next_invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_invoice_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("invoices.id"), nullable=True
    )
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    client: Mapped["Client"] = relationship("Client", lazy="selectin")
    last_invoice: Mapped[Optional["Invoice"]] = relationship(
        "Invoice", foreign_keys=[last_invoice_id], lazy="selectin"
    )

    __table_args__ = (
        Index("idx_recurring_client", "client_id"),
        Index("idx_recurring_next_date", "next_invoice_date"),
        Index("idx_recurring_active", "is_active"),
    )


# Engine and session management
settings = get_settings()

# Ensure database URL uses async driver
db_url = settings.database_url
if db_url.startswith("sqlite://"):
    db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)

engine = create_async_engine(
    db_url,
    echo=False,
    # SQLite connection pool configuration
    pool_pre_ping=True,  # Verify connections before use
    connect_args={"check_same_thread": False},  # Allow multi-threaded access
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
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
