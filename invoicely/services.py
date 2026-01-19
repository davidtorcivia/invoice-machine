"""Business logic services for invoices, clients, and backups."""

import gzip
import shutil
import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from invoicely.config import get_settings
from invoicely.database import (
    BusinessProfile,
    Client,
    Invoice,
    InvoiceItem,
)


async def generate_invoice_number(
    session: AsyncSession, issue_date: date, document_type: str = "invoice"
) -> str:
    """
    Generate invoice/quote number.

    Format: YYYYMMDD-N for invoices, Q-YYYYMMDD-N for quotes.
    The sequence number N resets for each date.
    """
    date_prefix = issue_date.strftime("%Y%m%d")
    prefix = "Q-" if document_type == "quote" else ""
    search_prefix = f"{prefix}{date_prefix}"

    # Find highest sequence for this date
    # Include deleted invoices to avoid UNIQUE constraint violations
    result = await session.execute(
        select(Invoice.invoice_number).where(
            Invoice.invoice_number.like(f"{search_prefix}-%"),
        )
    )
    existing_numbers = result.scalars().all()

    # Robust parsing - ignore malformed numbers
    max_seq = 0
    for num in existing_numbers:
        try:
            # Handle both "YYYYMMDD-N" and "Q-YYYYMMDD-N" formats
            if num.startswith("Q-"):
                parts = num[2:].split("-")  # Remove "Q-" prefix
            else:
                parts = num.split("-")
            if len(parts) == 2 and parts[0] == date_prefix:
                max_seq = max(max_seq, int(parts[1]))
        except (ValueError, IndexError):
            continue

    return f"{prefix}{date_prefix}-{max_seq + 1}"


def calculate_due_date(
    issue_date: date,
    payment_terms_days: Optional[int] = None,
    explicit_due_date: Optional[date] = None,
    client: Optional[Client] = None,
    business: Optional[BusinessProfile] = None,
) -> date:
    """
    Calculate invoice due date.

    Priority:
    1. Explicit due_date override
    2. Invoice's payment_terms_days
    3. Client's payment_terms_days
    4. Business default_payment_terms_days
    5. Default 30 days
    """
    if explicit_due_date:
        return explicit_due_date

    terms = (
        payment_terms_days
        or (client.payment_terms_days if client else None)
        or (business.default_payment_terms_days if business else None)
        or 30
    )

    return issue_date + timedelta(days=terms)


async def recalculate_invoice_totals(session: AsyncSession, invoice: Invoice):
    """Recalculate subtotal, tax, and total from line items."""
    result = await session.execute(
        select(InvoiceItem.total).where(InvoiceItem.invoice_id == invoice.id)
    )
    item_totals = result.scalars().all()

    subtotal = sum(Decimal(str(t)) for t in item_totals)
    invoice.subtotal = subtotal

    # Calculate tax if enabled
    if invoice.tax_enabled and invoice.tax_rate and invoice.tax_rate > 0:
        invoice.tax_amount = (subtotal * invoice.tax_rate / Decimal("100")).quantize(
            Decimal("0.01")
        )
    else:
        invoice.tax_amount = Decimal("0.00")

    invoice.total = subtotal + invoice.tax_amount


async def snapshot_client_info(
    session: AsyncSession, client: Client, invoice: Invoice
):
    """Copy client info to invoice for permanent record."""
    invoice.client_name = client.name
    invoice.client_business = client.business_name
    invoice.client_email = client.email

    # Build full address in standard format
    address_lines = []

    # Line 1: Street address (address_line1, address_line2)
    street_parts = [p for p in [client.address_line1, client.address_line2] if p]
    if street_parts:
        address_lines.append(", ".join(street_parts))

    # Line 2: City, State Postal
    city_line_parts = []
    if client.city:
        city_line_parts.append(client.city)
    if client.state:
        city_line_parts.append(client.state)
    if city_line_parts:
        city_line = ", ".join(city_line_parts)
        if client.postal_code:
            city_line += " " + client.postal_code
        address_lines.append(city_line)
    elif client.postal_code:
        address_lines.append(client.postal_code)

    # Line 3: Country (if provided)
    if client.country:
        address_lines.append(client.country)

    invoice.client_address = "\n".join(address_lines) if address_lines else None


def format_currency(amount: Decimal | float, currency_code: str = "USD") -> str:
    """Format amount as currency string."""
    amount = Decimal(str(amount))
    if currency_code == "USD":
        return f"${amount:,.2f}"
    return f"{amount:,.2f} {currency_code}"


class ClientService:
    """Service for client operations."""

    @staticmethod
    async def get_client_invoice_stats(
        session: AsyncSession,
        client_id: Optional[int] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get invoice statistics for clients using a single aggregated query.

        This avoids N+1 queries by using SQL aggregation with GROUP BY.

        Args:
            session: Database session
            client_id: Optional specific client ID to filter by
            limit: Maximum number of clients to return

        Returns:
            List of dicts with client info and invoice statistics
        """
        from sqlalchemy import func, case

        # Build aggregated query
        query = (
            select(
                Client.id,
                Client.name,
                Client.business_name,
                Client.email,
                func.coalesce(func.sum(Invoice.total), 0).label("total_invoiced"),
                func.coalesce(
                    func.sum(
                        case(
                            (Invoice.status == "paid", Invoice.total),
                            else_=0,
                        )
                    ),
                    0,
                ).label("total_paid"),
                func.count(Invoice.id).label("invoice_count"),
                func.sum(
                    case(
                        (Invoice.status == "paid", 1),
                        else_=0,
                    )
                ).label("paid_invoice_count"),
                func.min(Invoice.issue_date).label("first_invoice"),
                func.max(Invoice.issue_date).label("last_invoice"),
            )
            .outerjoin(
                Invoice,
                and_(
                    Invoice.client_id == Client.id,
                    Invoice.deleted_at.is_(None),
                ),
            )
            .where(Client.deleted_at.is_(None))
            .group_by(Client.id)
        )

        if client_id:
            query = query.where(Client.id == client_id)

        query = query.limit(limit)

        result = await session.execute(query)
        rows = result.all()

        return [
            {
                "client_id": row.id,
                "name": row.business_name or row.name or "Unknown",
                "email": row.email,
                "total_invoiced": Decimal(str(row.total_invoiced)),
                "total_paid": Decimal(str(row.total_paid)),
                "invoice_count": row.invoice_count or 0,
                "paid_invoice_count": row.paid_invoice_count or 0,
                "first_invoice": row.first_invoice,
                "last_invoice": row.last_invoice,
            }
            for row in rows
        ]

    @staticmethod
    async def list_clients(
        session: AsyncSession,
        search: Optional[str] = None,
        include_deleted: bool = False,
    ) -> list[Client]:
        """List clients with optional search."""
        query = select(Client)

        if not include_deleted:
            query = query.where(Client.deleted_at.is_(None))

        if search:
            search_term = f"%{search}%"
            query = query.where(
                (Client.name.ilike(search_term)) | (Client.business_name.ilike(search_term))
            )

        query = query.order_by(Client.created_at.desc())
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_client(session: AsyncSession, client_id: int) -> Optional[Client]:
        """Get client by ID."""
        return await session.get(Client, client_id)

    @staticmethod
    async def create_client(session: AsyncSession, **kwargs) -> Client:
        """Create new client."""
        client = Client(**kwargs)
        session.add(client)
        await session.commit()
        await session.refresh(client)
        return client

    @staticmethod
    async def update_client(
        session: AsyncSession, client_id: int, **kwargs
    ) -> Optional[Client]:
        """Update client."""
        client = await ClientService.get_client(session, client_id)
        if not client:
            return None

        for key, value in kwargs.items():
            if hasattr(client, key) and value is not None:
                setattr(client, key, value)

        client.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(client)
        return client

    @staticmethod
    async def delete_client(session: AsyncSession, client_id: int) -> bool:
        """Soft delete client (move to trash)."""
        client = await ClientService.get_client(session, client_id)
        if not client:
            return False

        client.deleted_at = datetime.utcnow()
        client.updated_at = datetime.utcnow()
        await session.commit()
        return True

    @staticmethod
    async def restore_client(session: AsyncSession, client_id: int) -> bool:
        """Restore soft deleted client."""
        query = select(Client).where(
            and_(Client.id == client_id, Client.deleted_at.is_not(None))
        )
        result = await session.execute(query)
        client = result.scalar_one_or_none()

        if not client:
            return False

        client.deleted_at = None
        client.updated_at = datetime.utcnow()
        await session.commit()
        return True


class InvoiceService:
    """Service for invoice operations."""

    @staticmethod
    async def list_invoices(
        session: AsyncSession,
        status: Optional[str] = None,
        client_id: Optional[int] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        include_deleted: bool = False,
        limit: int = 50,
    ) -> list[Invoice]:
        """List invoices with filters."""
        query = select(Invoice)

        if not include_deleted:
            query = query.where(Invoice.deleted_at.is_(None))

        if status:
            query = query.where(Invoice.status == status)

        if client_id:
            query = query.where(Invoice.client_id == client_id)

        if from_date:
            query = query.where(Invoice.issue_date >= from_date)

        if to_date:
            query = query.where(Invoice.issue_date <= to_date)

        query = query.order_by(Invoice.created_at.desc()).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_invoice(session: AsyncSession, invoice_id: int) -> Optional[Invoice]:
        """Get invoice by ID with items."""
        return await session.get(Invoice, invoice_id)

    @staticmethod
    async def create_invoice(
        session: AsyncSession,
        client_id: Optional[int] = None,
        issue_date: Optional[date] = None,
        due_date: Optional[date] = None,
        payment_terms_days: Optional[int] = None,
        currency_code: str = "USD",
        notes: Optional[str] = None,
        items: Optional[list[dict]] = None,
        document_type: str = "invoice",
        client_reference: Optional[str] = None,
        show_payment_instructions: bool = True,
        selected_payment_methods: Optional[str] = None,
        invoice_number_override: Optional[str] = None,
        tax_enabled: Optional[bool] = None,
        tax_rate: Optional[Decimal] = None,
        tax_name: Optional[str] = None,
    ) -> Invoice:
        """
        Create new invoice or quote.

        If client_id is provided, fetch client and snapshot info.
        Items format: [{description, quantity, unit_price, unit_type}]
        Tax settings are snapshotted from business profile if not provided.
        """
        from invoicely.config import get_settings
        settings = get_settings()
        business = await BusinessProfile.get_or_create(session)

        # Validate tax_rate if provided
        if tax_rate is not None and (tax_rate < 0 or tax_rate > 100):
            raise ValueError("Tax rate must be between 0 and 100")

        # Get client if provided
        client = None
        if client_id:
            client = await session.get(Client, client_id)

        # Determine tax settings with cascade: invoice param > client setting > global default
        # Tax enabled
        if tax_enabled is not None:
            use_tax_enabled = tax_enabled
        elif client and client.tax_enabled is not None:
            use_tax_enabled = bool(client.tax_enabled)
        else:
            use_tax_enabled = bool(business.default_tax_enabled)

        # Tax rate
        if tax_rate is not None:
            use_tax_rate = tax_rate
        elif client and client.tax_rate is not None:
            use_tax_rate = client.tax_rate
        else:
            use_tax_rate = business.default_tax_rate

        # Tax name
        if tax_name is not None:
            use_tax_name = tax_name
        elif client and client.tax_name is not None:
            use_tax_name = client.tax_name
        else:
            use_tax_name = business.default_tax_name

        # Generate invoice number or use override
        invoice_date = issue_date or date.today()
        if invoice_number_override:
            invoice_number = invoice_number_override
        else:
            invoice_number = await generate_invoice_number(session, invoice_date, document_type)

        # Calculate due date
        calculated_due_date = calculate_due_date(
            invoice_date, payment_terms_days, due_date, client, business
        )

        # Create invoice
        invoice = Invoice(
            invoice_number=invoice_number,
            client_id=client_id,
            issue_date=invoice_date,
            due_date=calculated_due_date,
            payment_terms_days=payment_terms_days
            or (client.payment_terms_days if client else None)
            or business.default_payment_terms_days,
            currency_code=currency_code,
            notes=notes,
            status="draft",
            document_type=document_type,
            client_reference=client_reference,
            show_payment_instructions=1 if show_payment_instructions else 0,
            selected_payment_methods=selected_payment_methods,
            # Tax settings (snapshotted at creation time)
            tax_enabled=1 if use_tax_enabled else 0,
            tax_rate=use_tax_rate or Decimal("0.00"),
            tax_name=use_tax_name or "Tax",
        )

        # Snapshot client info
        if client:
            await snapshot_client_info(session, client, invoice)

        session.add(invoice)
        await session.flush()  # Get invoice.id

        # Add items if provided
        if items:
            for i, item_data in enumerate(items):
                await InvoiceService.add_item(
                    session,
                    invoice.id,
                    item_data.get("description", ""),
                    item_data.get("quantity", 1),
                    item_data.get("unit_price", 0),
                    sort_order=i,
                    unit_type=item_data.get("unit_type", "qty"),
                )

        await recalculate_invoice_totals(session, invoice)
        await session.commit()
        await session.refresh(invoice)

        return invoice

    @staticmethod
    async def update_invoice(
        session: AsyncSession,
        invoice_id: int,
        issue_date: Optional[date] = None,
        due_date: Optional[date] = None,
        status: Optional[str] = None,
        notes: Optional[str] = None,
        **kwargs,
    ) -> Optional[Invoice]:
        """Update invoice fields."""
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            return None

        business = await BusinessProfile.get_or_create(session)
        client = None
        if invoice.client_id:
            client = await session.get(Client, invoice.client_id)

        # Handle issue_date change - regenerate invoice number
        if issue_date and issue_date != invoice.issue_date:
            invoice.issue_date = issue_date
            invoice.invoice_number = await generate_invoice_number(session, issue_date)
            # Recalculate due date if not explicitly overridden
            if not due_date:
                invoice.due_date = calculate_due_date(
                    issue_date, invoice.payment_terms_days, None, client, business
                )

        if due_date:
            invoice.due_date = due_date

        if status:
            valid_statuses = ["draft", "sent", "paid", "overdue", "cancelled"]
            if status not in valid_statuses:
                raise ValueError(f"Invalid status. Must be one of: {valid_statuses}")
            invoice.status = status

        if notes is not None:
            invoice.notes = notes

        for key, value in kwargs.items():
            if hasattr(invoice, key) and value is not None:
                setattr(invoice, key, value)

        # Re-snapshot client info to ensure address format is current
        if client:
            await snapshot_client_info(session, client, invoice)

        invoice.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(invoice)
        return invoice

    @staticmethod
    async def delete_invoice(session: AsyncSession, invoice_id: int) -> bool:
        """Soft delete invoice (move to trash)."""
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            return False

        invoice.deleted_at = datetime.utcnow()
        invoice.updated_at = datetime.utcnow()
        await session.commit()
        return True

    @staticmethod
    async def restore_invoice(session: AsyncSession, invoice_id: int) -> bool:
        """Restore soft deleted invoice."""
        query = select(Invoice).where(
            and_(Invoice.id == invoice_id, Invoice.deleted_at.is_not(None))
        )
        result = await session.execute(query)
        invoice = result.scalar_one_or_none()

        if not invoice:
            return False

        invoice.deleted_at = None
        invoice.updated_at = datetime.utcnow()
        await session.commit()
        return True

    @staticmethod
    async def add_item(
        session: AsyncSession,
        invoice_id: int,
        description: str,
        quantity: int = 1,
        unit_price: Decimal | float | str = 0,
        sort_order: int = 0,
        unit_type: str = "qty",
    ) -> InvoiceItem:
        """Add line item to invoice."""
        # Validate inputs
        if quantity < 0:
            raise ValueError("Quantity cannot be negative")

        unit_price = Decimal(str(unit_price))
        if unit_price < 0:
            raise ValueError("Unit price cannot be negative")

        valid_unit_types = ["qty", "hours"]
        if unit_type not in valid_unit_types:
            raise ValueError(f"Invalid unit type. Must be one of: {valid_unit_types}")

        total = unit_price * Decimal(quantity)

        item = InvoiceItem(
            invoice_id=invoice_id,
            description=description,
            quantity=quantity,
            unit_type=unit_type,
            unit_price=unit_price,
            total=total,
            sort_order=sort_order,
        )
        session.add(item)
        await session.flush()

        # Update invoice totals
        invoice = await session.get(Invoice, invoice_id)
        if invoice:
            await recalculate_invoice_totals(session, invoice)

        await session.commit()
        await session.refresh(item)
        return item

    @staticmethod
    async def update_item(
        session: AsyncSession,
        item_id: int,
        description: Optional[str] = None,
        quantity: Optional[int] = None,
        unit_price: Optional[Decimal | float | str] = None,
        sort_order: Optional[int] = None,
        unit_type: Optional[str] = None,
        invoice_id: Optional[int] = None,
    ) -> Optional[InvoiceItem]:
        """
        Update line item.

        Args:
            session: Database session
            item_id: ID of the item to update
            description: New description (optional)
            quantity: New quantity (optional)
            unit_price: New unit price (optional)
            sort_order: New sort order (optional)
            unit_type: New unit type (optional)
            invoice_id: If provided, validates that the item belongs to this invoice

        Returns:
            Updated item or None if not found

        Raises:
            ValueError: If invoice_id is provided but item doesn't belong to that invoice
        """
        item = await session.get(InvoiceItem, item_id)
        if not item:
            return None

        # Validate item belongs to specified invoice (IDOR protection)
        if invoice_id is not None and item.invoice_id != invoice_id:
            raise ValueError("Item does not belong to the specified invoice")

        # Validate inputs
        if quantity is not None and quantity < 0:
            raise ValueError("Quantity cannot be negative")
        if unit_price is not None:
            unit_price_decimal = Decimal(str(unit_price))
            if unit_price_decimal < 0:
                raise ValueError("Unit price cannot be negative")
        if unit_type is not None:
            valid_unit_types = ["qty", "hours"]
            if unit_type not in valid_unit_types:
                raise ValueError(f"Invalid unit type. Must be one of: {valid_unit_types}")

        if description is not None:
            item.description = description
        if quantity is not None:
            item.quantity = quantity
        if unit_price is not None:
            item.unit_price = Decimal(str(unit_price))
        if sort_order is not None:
            item.sort_order = sort_order
        if unit_type is not None:
            item.unit_type = unit_type

        # Recalculate total
        item.total = item.unit_price * Decimal(str(item.quantity))

        # Update invoice totals
        await recalculate_invoice_totals(session, item.invoice)

        await session.commit()
        await session.refresh(item)
        return item

    @staticmethod
    async def remove_item(
        session: AsyncSession,
        item_id: int,
        invoice_id: Optional[int] = None,
    ) -> bool:
        """
        Remove line item.

        Args:
            session: Database session
            item_id: ID of the item to remove
            invoice_id: If provided, validates that the item belongs to this invoice

        Returns:
            True if item was removed, False if not found

        Raises:
            ValueError: If invoice_id is provided but item doesn't belong to that invoice
        """
        item = await session.get(InvoiceItem, item_id)
        if not item:
            return False

        # Validate item belongs to specified invoice (IDOR protection)
        if invoice_id is not None and item.invoice_id != invoice_id:
            raise ValueError("Item does not belong to the specified invoice")

        item_invoice_id = item.invoice_id
        await session.delete(item)

        # Update invoice totals
        invoice = await session.get(Invoice, item_invoice_id)
        if invoice:
            await recalculate_invoice_totals(session, invoice)

        await session.commit()
        return True

    @staticmethod
    async def update_overdue_invoices(session: AsyncSession) -> int:
        """
        Mark sent invoices as overdue if due_date < today.

        Returns the count of invoices updated.
        """
        today = date.today()
        result = await session.execute(
            update(Invoice)
            .where(
                and_(
                    Invoice.status == "sent",
                    Invoice.due_date < today,
                    Invoice.deleted_at.is_(None),
                )
            )
            .values(status="overdue", updated_at=datetime.utcnow())
        )
        await session.commit()
        return result.rowcount


class BackupService:
    """Service for creating and managing backups."""

    def __init__(
        self,
        backup_dir: Optional[Path] = None,
        retention_days: int = 30,
        s3_config: Optional[dict] = None,
    ):
        settings = get_settings()
        self.backup_dir = backup_dir or settings.data_dir / "backups"
        self.retention_days = retention_days
        self.s3_config = s3_config
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, compress: bool = True) -> dict:
        """
        Create a backup of the database and return backup info.

        Returns dict with: filename, path, size_bytes, timestamp, uploaded_to_s3
        """
        settings = get_settings()
        timestamp = datetime.utcnow()
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")

        # Source database
        db_path = settings.data_dir / "invoicely.db"
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found at {db_path}")

        # Create backup filename
        if compress:
            backup_filename = f"invoicely_backup_{timestamp_str}.db.gz"
        else:
            backup_filename = f"invoicely_backup_{timestamp_str}.db"

        backup_path = self.backup_dir / backup_filename

        # Copy and optionally compress
        if compress:
            with open(db_path, "rb") as f_in:
                with gzip.open(backup_path, "wb", compresslevel=6) as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(db_path, backup_path)

        size_bytes = backup_path.stat().st_size

        result = {
            "filename": backup_filename,
            "path": str(backup_path),
            "size_bytes": size_bytes,
            "timestamp": timestamp.isoformat(),
            "compressed": compress,
            "uploaded_to_s3": False,
        }

        # Upload to S3 if configured
        if self.s3_config and self.s3_config.get("enabled"):
            try:
                self._upload_to_s3(backup_path, backup_filename)
                result["uploaded_to_s3"] = True
            except Exception as e:
                result["s3_error"] = str(e)

        return result

    def _upload_to_s3(self, local_path: Path, filename: str):
        """Upload backup to S3-compatible storage."""
        config = self.s3_config
        if not config:
            raise ValueError("S3 configuration not provided")

        # Create S3 client
        s3_client = boto3.client(
            "s3",
            endpoint_url=config.get("endpoint_url"),
            aws_access_key_id=config.get("access_key_id"),
            aws_secret_access_key=config.get("secret_access_key"),
            region_name=config.get("region", "auto"),
            config=Config(signature_version="s3v4"),
        )

        bucket = config.get("bucket")
        prefix = config.get("prefix", "invoice-machine-backups")
        key = f"{prefix}/{filename}"

        s3_client.upload_file(str(local_path), bucket, key)

    def list_backups(self) -> list[dict]:
        """List all local backups sorted by date (newest first)."""
        backups = []
        for path in self.backup_dir.glob("invoicely_backup_*.db*"):
            stat = path.stat()
            backups.append({
                "filename": path.name,
                "path": str(path),
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "compressed": path.suffix == ".gz",
            })

        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return backups

    def cleanup_old_backups(self) -> int:
        """
        Delete backups older than retention_days.

        Returns number of backups deleted.
        """
        cutoff = datetime.utcnow() - timedelta(days=self.retention_days)
        deleted = 0

        for path in self.backup_dir.glob("invoicely_backup_*.db*"):
            stat = path.stat()
            created = datetime.fromtimestamp(stat.st_mtime)
            if created < cutoff:
                path.unlink()
                deleted += 1

        # Also cleanup S3 if configured
        if self.s3_config and self.s3_config.get("enabled"):
            try:
                deleted += self._cleanup_s3_backups(cutoff)
            except Exception:
                pass  # Don't fail if S3 cleanup fails

        return deleted

    def _cleanup_s3_backups(self, cutoff: datetime) -> int:
        """Delete old backups from S3."""
        config = self.s3_config
        if not config:
            return 0

        s3_client = boto3.client(
            "s3",
            endpoint_url=config.get("endpoint_url"),
            aws_access_key_id=config.get("access_key_id"),
            aws_secret_access_key=config.get("secret_access_key"),
            region_name=config.get("region", "auto"),
            config=Config(signature_version="s3v4"),
        )

        bucket = config.get("bucket")
        prefix = config.get("prefix", "invoice-machine-backups")

        # List objects
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        deleted = 0

        for obj in response.get("Contents", []):
            if obj["LastModified"].replace(tzinfo=None) < cutoff:
                s3_client.delete_object(Bucket=bucket, Key=obj["Key"])
                deleted += 1

        return deleted

    def validate_backup(self, backup_path: Path) -> bool:
        """
        Validate that a backup file is a valid SQLite database.

        Returns True if valid, raises exception if not.
        """
        # If compressed, decompress to temp file for validation
        if backup_path.suffix == ".gz":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                tmp_path = Path(tmp.name)
            try:
                with gzip.open(backup_path, "rb") as f_in:
                    with open(tmp_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                test_path = tmp_path
            except Exception as e:
                tmp_path.unlink(missing_ok=True)
                raise ValueError(f"Failed to decompress backup: {e}")
        else:
            test_path = backup_path
            tmp_path = None

        try:
            # Try to open and query the database
            conn = sqlite3.connect(test_path)
            cursor = conn.cursor()

            # Check for expected tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}

            required_tables = {"users", "business_profile", "clients", "invoices", "invoice_items"}
            missing = required_tables - tables

            conn.close()

            if missing:
                raise ValueError(f"Backup is missing required tables: {missing}")

            return True
        except sqlite3.Error as e:
            raise ValueError(f"Invalid SQLite database: {e}")
        finally:
            if tmp_path:
                tmp_path.unlink(missing_ok=True)

    def _validate_backup_filename(self, filename: str) -> Path:
        """
        Validate backup filename and return safe path.

        Prevents path traversal attacks by ensuring the resolved path
        stays within the backup directory.

        Args:
            filename: The backup filename to validate

        Returns:
            Safe Path object within backup_dir

        Raises:
            ValueError: If filename contains path traversal attempts
        """
        # Reject any path separators
        if "/" in filename or "\\" in filename:
            raise ValueError("Invalid backup filename: path separators not allowed")

        # Reject parent directory references
        if ".." in filename:
            raise ValueError("Invalid backup filename: parent directory reference not allowed")

        # Build path and verify it resolves within backup_dir
        backup_path = self.backup_dir / filename
        try:
            resolved = backup_path.resolve()
            backup_dir_resolved = self.backup_dir.resolve()
            if not str(resolved).startswith(str(backup_dir_resolved)):
                raise ValueError("Invalid backup filename: path traversal detected")
        except (OSError, ValueError) as e:
            raise ValueError(f"Invalid backup filename: {e}")

        return backup_path

    def restore_backup(self, backup_filename: str, validate: bool = True) -> dict:
        """
        Restore database from a backup file.

        This is a graceful restore that:
        1. Validates the backup file integrity
        2. Creates a pre-restore backup of current database
        3. Performs the restore
        4. Returns information about the restore operation

        Warning: This will overwrite the current database!
        The application should be restarted after restore.
        """
        settings = get_settings()
        backup_path = self._validate_backup_filename(backup_filename)
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_filename}")

        # Validate backup before proceeding
        if validate:
            self.validate_backup(backup_path)

        db_path = settings.data_dir / "invoicely.db"
        pre_restore_filename = None

        # Create a backup of current database before restoring
        if db_path.exists():
            pre_restore_filename = f"pre_restore_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db"
            pre_restore_backup = self.backup_dir / pre_restore_filename
            shutil.copy2(db_path, pre_restore_backup)

        # Restore
        if backup_path.suffix == ".gz":
            with gzip.open(backup_path, "rb") as f_in:
                with open(db_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(backup_path, db_path)

        return {
            "restored_from": backup_filename,
            "pre_restore_backup": pre_restore_filename,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Database restored. Please restart the application for changes to take effect.",
        }

    def download_from_s3(self, filename: str) -> Path:
        """Download a backup from S3 to local backup directory."""
        config = self.s3_config
        if not config or not config.get("enabled"):
            raise ValueError("S3 is not configured")

        # Validate filename to prevent path traversal
        local_path = self._validate_backup_filename(filename)

        s3_client = boto3.client(
            "s3",
            endpoint_url=config.get("endpoint_url"),
            aws_access_key_id=config.get("access_key_id"),
            aws_secret_access_key=config.get("secret_access_key"),
            region_name=config.get("region", "auto"),
            config=Config(signature_version="s3v4"),
        )

        bucket = config.get("bucket")
        prefix = config.get("prefix", "invoice-machine-backups")
        key = f"{prefix}/{filename}"

        s3_client.download_file(bucket, key, str(local_path))

        return local_path

    def list_s3_backups(self) -> list[dict]:
        """List backups stored in S3."""
        config = self.s3_config
        if not config or not config.get("enabled"):
            return []

        try:
            s3_client = boto3.client(
                "s3",
                endpoint_url=config.get("endpoint_url"),
                aws_access_key_id=config.get("access_key_id"),
                aws_secret_access_key=config.get("secret_access_key"),
                region_name=config.get("region", "auto"),
                config=Config(signature_version="s3v4"),
            )

            bucket = config.get("bucket")
            prefix = config.get("prefix", "invoice-machine-backups")

            response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            backups = []

            for obj in response.get("Contents", []):
                filename = obj["Key"].split("/")[-1]
                if filename.startswith("invoicely_backup_"):
                    backups.append({
                        "filename": filename,
                        "size_bytes": obj["Size"],
                        "created_at": obj["LastModified"].isoformat(),
                        "location": "s3",
                    })

            backups.sort(key=lambda x: x["created_at"], reverse=True)
            return backups
        except Exception:
            return []

    def delete_backup(self, backup_filename: str) -> bool:
        """Delete a specific backup file."""
        # Validate filename to prevent path traversal
        backup_path = self._validate_backup_filename(backup_filename)
        if backup_path.exists():
            backup_path.unlink()
            return True
        return False


def get_backup_service(
    retention_days: Optional[int] = None,
    s3_config: Optional[dict] = None,
) -> BackupService:
    """Get a BackupService instance with optional configuration."""
    return BackupService(
        retention_days=retention_days or 30,
        s3_config=s3_config,
    )


class RecurringService:
    """Service for managing recurring invoice schedules."""

    @staticmethod
    async def create_schedule(
        session: AsyncSession,
        client_id: int,
        name: str,
        frequency: str,
        schedule_day: int = 1,
        currency_code: str = "USD",
        payment_terms_days: int = 30,
        notes: Optional[str] = None,
        line_items: Optional[list] = None,
        tax_enabled: Optional[int] = None,
        tax_rate: Optional[Decimal] = None,
        tax_name: Optional[str] = None,
        next_invoice_date: Optional[date] = None,
    ) -> "RecurringSchedule":
        """Create a new recurring schedule."""
        from invoicely.database import RecurringSchedule
        import json
        from dateutil.relativedelta import relativedelta

        # Validate frequency
        valid_frequencies = ["daily", "weekly", "monthly", "quarterly", "yearly"]
        if frequency not in valid_frequencies:
            raise ValueError(f"Invalid frequency. Must be one of: {valid_frequencies}")

        # Validate schedule_day
        if frequency == "weekly" and not (0 <= schedule_day <= 6):
            raise ValueError("For weekly frequency, schedule_day must be 0-6 (Monday-Sunday)")
        elif frequency in ["monthly", "quarterly", "yearly"] and not (1 <= schedule_day <= 31):
            raise ValueError("For monthly/quarterly/yearly frequency, schedule_day must be 1-31")

        # Validate payment_terms_days
        if payment_terms_days < 0 or payment_terms_days > 365:
            raise ValueError("Payment terms must be between 0 and 365 days")

        # Validate tax_rate if provided
        if tax_rate is not None and (tax_rate < 0 or tax_rate > 100):
            raise ValueError("Tax rate must be between 0 and 100")

        # Calculate next invoice date if not provided
        if next_invoice_date is None:
            today = date.today()
            if frequency == "daily":
                next_invoice_date = today + timedelta(days=1)
            elif frequency == "weekly":
                # Next occurrence of schedule_day (0=Monday, 6=Sunday)
                days_ahead = schedule_day - today.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                next_invoice_date = today + timedelta(days=days_ahead)
            elif frequency == "monthly":
                # Next month on schedule_day
                next_invoice_date = (today.replace(day=1) + relativedelta(months=1)).replace(
                    day=min(schedule_day, 28)
                )
            elif frequency == "quarterly":
                # Next quarter on schedule_day
                next_invoice_date = (today.replace(day=1) + relativedelta(months=3)).replace(
                    day=min(schedule_day, 28)
                )
            elif frequency == "yearly":
                # Next year on schedule_day (of current month)
                next_invoice_date = (today.replace(day=1) + relativedelta(years=1)).replace(
                    day=min(schedule_day, 28)
                )

        schedule = RecurringSchedule(
            client_id=client_id,
            name=name,
            frequency=frequency,
            schedule_day=schedule_day,
            currency_code=currency_code,
            payment_terms_days=payment_terms_days,
            notes=notes,
            line_items=json.dumps(line_items) if line_items else None,
            tax_enabled=tax_enabled,
            tax_rate=tax_rate,
            tax_name=tax_name,
            next_invoice_date=next_invoice_date,
        )
        session.add(schedule)
        await session.commit()
        await session.refresh(schedule)
        return schedule

    @staticmethod
    async def get_schedule(
        session: AsyncSession, schedule_id: int
    ) -> Optional["RecurringSchedule"]:
        """Get a recurring schedule by ID."""
        from invoicely.database import RecurringSchedule
        from sqlalchemy import select

        result = await session.execute(
            select(RecurringSchedule).where(RecurringSchedule.id == schedule_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_schedules(
        session: AsyncSession,
        client_id: Optional[int] = None,
        active_only: bool = True,
    ) -> list["RecurringSchedule"]:
        """List recurring schedules."""
        from invoicely.database import RecurringSchedule
        from sqlalchemy import select

        query = select(RecurringSchedule)
        if client_id:
            query = query.where(RecurringSchedule.client_id == client_id)
        if active_only:
            query = query.where(RecurringSchedule.is_active == 1)
        query = query.order_by(RecurringSchedule.next_invoice_date)

        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def update_schedule(
        session: AsyncSession, schedule_id: int, **kwargs
    ) -> Optional["RecurringSchedule"]:
        """Update a recurring schedule."""
        import json

        schedule = await RecurringService.get_schedule(session, schedule_id)
        if not schedule:
            return None

        # Handle line_items JSON conversion
        if "line_items" in kwargs and kwargs["line_items"] is not None:
            kwargs["line_items"] = json.dumps(kwargs["line_items"])

        for key, value in kwargs.items():
            if hasattr(schedule, key) and value is not None:
                setattr(schedule, key, value)

        schedule.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(schedule)
        return schedule

    @staticmethod
    async def delete_schedule(session: AsyncSession, schedule_id: int) -> bool:
        """Delete a recurring schedule."""
        from invoicely.database import RecurringSchedule

        schedule = await RecurringService.get_schedule(session, schedule_id)
        if not schedule:
            return False

        await session.delete(schedule)
        await session.commit()
        return True

    @staticmethod
    async def pause_schedule(session: AsyncSession, schedule_id: int) -> bool:
        """Pause a recurring schedule."""
        schedule = await RecurringService.get_schedule(session, schedule_id)
        if not schedule:
            return False

        schedule.is_active = 0
        schedule.updated_at = datetime.utcnow()
        await session.commit()
        return True

    @staticmethod
    async def resume_schedule(session: AsyncSession, schedule_id: int) -> bool:
        """Resume a paused recurring schedule."""
        schedule = await RecurringService.get_schedule(session, schedule_id)
        if not schedule:
            return False

        schedule.is_active = 1
        schedule.updated_at = datetime.utcnow()
        await session.commit()
        return True

    @staticmethod
    def calculate_next_date(current_date: date, frequency: str, schedule_day: int) -> date:
        """Calculate the next invoice date based on frequency."""
        from dateutil.relativedelta import relativedelta

        if frequency == "daily":
            return current_date + timedelta(days=1)
        elif frequency == "weekly":
            return current_date + timedelta(weeks=1)
        elif frequency == "monthly":
            next_date = current_date + relativedelta(months=1)
            # Handle months with fewer days
            try:
                return next_date.replace(day=schedule_day)
            except ValueError:
                # Day doesn't exist in this month, use last day
                return (next_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)
        elif frequency == "quarterly":
            next_date = current_date + relativedelta(months=3)
            try:
                return next_date.replace(day=schedule_day)
            except ValueError:
                return (next_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)
        elif frequency == "yearly":
            next_date = current_date + relativedelta(years=1)
            try:
                return next_date.replace(day=schedule_day)
            except ValueError:
                return (next_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)
        else:
            raise ValueError(f"Unknown frequency: {frequency}")

    @staticmethod
    async def process_due_schedules(session: AsyncSession) -> list[dict]:
        """Process all schedules due today or earlier and create invoices."""
        from invoicely.database import RecurringSchedule
        from sqlalchemy import select
        import json

        today = date.today()
        results = []

        # Find all active schedules where next_invoice_date <= today
        query = select(RecurringSchedule).where(
            RecurringSchedule.is_active == 1,
            RecurringSchedule.next_invoice_date <= today,
        )
        result = await session.execute(query)
        due_schedules = list(result.scalars().all())

        for schedule in due_schedules:
            try:
                # Parse line items
                line_items = json.loads(schedule.line_items) if schedule.line_items else []

                # Create invoice
                invoice = await InvoiceService.create_invoice(
                    session,
                    client_id=schedule.client_id,
                    issue_date=today,
                    currency_code=schedule.currency_code,
                    payment_terms_days=schedule.payment_terms_days,
                    notes=schedule.notes,
                    items=line_items,
                    tax_enabled=schedule.tax_enabled,
                    tax_rate=schedule.tax_rate,
                    tax_name=schedule.tax_name,
                )

                # Update schedule with next date and last invoice
                schedule.last_invoice_id = invoice.id
                schedule.next_invoice_date = RecurringService.calculate_next_date(
                    today, schedule.frequency, schedule.schedule_day
                )
                schedule.updated_at = datetime.utcnow()

                results.append({
                    "schedule_id": schedule.id,
                    "schedule_name": schedule.name,
                    "invoice_id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "success": True,
                })

            except Exception as e:
                results.append({
                    "schedule_id": schedule.id,
                    "schedule_name": schedule.name,
                    "success": False,
                    "error": str(e),
                })

        await session.commit()
        return results

    @staticmethod
    async def trigger_schedule(session: AsyncSession, schedule_id: int) -> dict:
        """Manually trigger a schedule to create an invoice now."""
        from invoicely.database import RecurringSchedule
        import json

        schedule = await RecurringService.get_schedule(session, schedule_id)
        if not schedule:
            return {"success": False, "error": "Schedule not found"}

        today = date.today()

        try:
            # Parse line items
            line_items = json.loads(schedule.line_items) if schedule.line_items else []

            # Create invoice
            invoice = await InvoiceService.create_invoice(
                session,
                client_id=schedule.client_id,
                issue_date=today,
                currency_code=schedule.currency_code,
                payment_terms_days=schedule.payment_terms_days,
                notes=schedule.notes,
                items=line_items,
                tax_enabled=schedule.tax_enabled,
                tax_rate=schedule.tax_rate,
                tax_name=schedule.tax_name,
            )

            # Update schedule with next date and last invoice
            schedule.last_invoice_id = invoice.id
            schedule.next_invoice_date = RecurringService.calculate_next_date(
                today, schedule.frequency, schedule.schedule_day
            )
            schedule.updated_at = datetime.utcnow()
            await session.commit()

            return {
                "success": True,
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "next_invoice_date": schedule.next_invoice_date.isoformat(),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


class SearchService:
    """Service for full-text search across invoices and clients."""

    @staticmethod
    async def reindex_fts(session: AsyncSession, force: bool = False) -> dict:
        """
        Rebuild FTS tables from main tables using FTS5 'rebuild' command.

        The FTS tables use 'content=' option (external content tables), which means
        they store only the tokenized index, not the actual content. The 'rebuild'
        command tells FTS5 to re-read all data from the content table and rebuild
        its index.

        Args:
            session: Database session
            force: If True, always rebuild even if FTS tables appear populated

        Returns:
            Dict with counts of indexed invoices, clients, and line items
        """
        from sqlalchemy import text

        result = {"invoices_indexed": 0, "clients_indexed": 0, "line_items_indexed": 0, "skipped": False, "rebuilt": False}

        try:
            # Check if FTS tables exist
            tables_check = await session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('invoices_fts', 'clients_fts', 'invoice_items_fts')")
            )
            existing_tables = {row[0] for row in tables_check.fetchall()}

            if "invoices_fts" not in existing_tables or "clients_fts" not in existing_tables:
                result["skipped"] = True
                result["reason"] = "FTS tables don't exist"
                return result

            # Create invoice_items_fts if it doesn't exist (migration may have failed)
            if "invoice_items_fts" not in existing_tables:
                await session.execute(text("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS invoice_items_fts USING fts5(
                        description,
                        content='invoice_items',
                        content_rowid='id'
                    )
                """))
                await session.execute(text("""
                    CREATE TRIGGER IF NOT EXISTS invoice_items_fts_insert AFTER INSERT ON invoice_items BEGIN
                        INSERT INTO invoice_items_fts(rowid, description)
                        VALUES (new.id, new.description);
                    END
                """))
                await session.execute(text("""
                    CREATE TRIGGER IF NOT EXISTS invoice_items_fts_delete AFTER DELETE ON invoice_items BEGIN
                        INSERT INTO invoice_items_fts(invoice_items_fts, rowid, description)
                        VALUES ('delete', old.id, old.description);
                    END
                """))
                await session.execute(text("""
                    CREATE TRIGGER IF NOT EXISTS invoice_items_fts_update AFTER UPDATE ON invoice_items BEGIN
                        INSERT INTO invoice_items_fts(invoice_items_fts, rowid, description)
                        VALUES ('delete', old.id, old.description);
                        INSERT INTO invoice_items_fts(rowid, description)
                        VALUES (new.id, new.description);
                    END
                """))
                await session.commit()

            # Get counts from main tables
            invoices_count = (await session.execute(text("SELECT COUNT(*) FROM invoices"))).scalar()
            clients_count = (await session.execute(text("SELECT COUNT(*) FROM clients"))).scalar()
            line_items_count = (await session.execute(text("SELECT COUNT(*) FROM invoice_items"))).scalar()

            # If no data to index, skip
            if invoices_count == 0 and clients_count == 0 and line_items_count == 0:
                result["skipped"] = True
                result["reason"] = "No data to index"
                return result

            # For external content FTS tables, use the 'rebuild' command
            # This re-reads all data from the content table and rebuilds the index
            # It's the correct way to sync FTS with external content tables
            if invoices_count > 0:
                await session.execute(text("INSERT INTO invoices_fts(invoices_fts) VALUES('rebuild')"))
                result["invoices_indexed"] = invoices_count

            if clients_count > 0:
                await session.execute(text("INSERT INTO clients_fts(clients_fts) VALUES('rebuild')"))
                result["clients_indexed"] = clients_count

            # Reindex line items (table created above if it didn't exist)
            if line_items_count > 0:
                await session.execute(text("INSERT INTO invoice_items_fts(invoice_items_fts) VALUES('rebuild')"))
                result["line_items_indexed"] = line_items_count

            await session.commit()
            result["rebuilt"] = True
            return result

        except Exception as e:
            result["error"] = str(e)
            return result

    @staticmethod
    async def search(
        session: AsyncSession,
        query: str,
        search_invoices: bool = True,
        search_clients: bool = True,
        search_line_items: bool = True,
        limit: int = 20,
    ) -> dict:
        """
        Search across invoices, clients, and line items using FTS5.

        Args:
            session: Database session
            query: Search query (supports FTS5 syntax)
            search_invoices: Include invoices in search
            search_clients: Include clients in search
            search_line_items: Include invoice line items in search
            limit: Maximum results per category

        Returns:
            Dict with 'invoices', 'clients', and 'line_items' lists
        """
        from sqlalchemy import text

        results = {"invoices": [], "clients": [], "line_items": []}

        # Validate and sanitize limit
        limit = max(1, min(limit, 100))  # Clamp between 1 and 100

        # Validate query
        if not query or not query.strip():
            return results

        # Escape query for FTS5 - escape all special FTS5 characters
        # FTS5 special chars: " * - ( ) : ^ AND OR NOT NEAR
        safe_query = query.strip()
        # Remove potentially dangerous FTS5 operators
        for char in ['"', '*', '-', '(', ')', ':', '^']:
            safe_query = safe_query.replace(char, ' ')
        # Replace FTS5 boolean operators with spaces
        for op in [' AND ', ' OR ', ' NOT ', ' NEAR ']:
            safe_query = safe_query.replace(op, ' ')
            safe_query = safe_query.replace(op.lower(), ' ')
        # Collapse multiple spaces and trim
        safe_query = ' '.join(safe_query.split())

        if not safe_query:
            return results

        # Add wildcards for partial matching - FTS5 requires wildcard on each word
        # "phrase"* is invalid FTS5 syntax, use word1* word2* instead
        words = safe_query.split()
        fts_query = ' '.join(f'{word}*' for word in words)

        if search_invoices:
            try:
                # Search invoices using FTS5
                invoice_sql = text("""
                    SELECT i.id, i.invoice_number, i.client_name, i.client_business,
                           i.status, i.total, i.currency_code, i.issue_date, i.deleted_at,
                           snippet(invoices_fts, 0, '<mark>', '</mark>', '...', 32) as match_snippet
                    FROM invoices_fts
                    JOIN invoices i ON invoices_fts.rowid = i.id
                    WHERE invoices_fts MATCH :query
                    ORDER BY rank
                    LIMIT :limit
                """)
                result = await session.execute(invoice_sql, {"query": fts_query, "limit": limit})
                for row in result.fetchall():
                    # issue_date may be string (from raw SQL) or datetime
                    issue_date = row.issue_date
                    if issue_date and hasattr(issue_date, 'isoformat'):
                        issue_date = issue_date.isoformat()
                    results["invoices"].append({
                        "id": row.id,
                        "invoice_number": row.invoice_number,
                        "client_name": row.client_name,
                        "client_business": row.client_business,
                        "status": row.status,
                        "total": str(row.total),
                        "currency_code": row.currency_code,
                        "issue_date": issue_date,
                        "is_deleted": row.deleted_at is not None,
                        "match_snippet": row.match_snippet,
                    })
            except Exception as e:
                # FTS tables might not exist yet or query error, fall back to LIKE search
                print(f"FTS invoice search error, falling back to LIKE: {e}", flush=True)
                results["invoices"] = await SearchService._fallback_invoice_search(
                    session, query, limit
                )

        if search_clients:
            try:
                # Search clients using FTS5
                client_sql = text("""
                    SELECT c.id, c.name, c.business_name, c.email, c.phone, c.deleted_at,
                           snippet(clients_fts, 0, '<mark>', '</mark>', '...', 32) as match_snippet
                    FROM clients_fts
                    JOIN clients c ON clients_fts.rowid = c.id
                    WHERE clients_fts MATCH :query
                    ORDER BY rank
                    LIMIT :limit
                """)
                result = await session.execute(client_sql, {"query": fts_query, "limit": limit})
                for row in result.fetchall():
                    results["clients"].append({
                        "id": row.id,
                        "name": row.name,
                        "business_name": row.business_name,
                        "display_name": row.business_name or row.name or "Unknown",
                        "email": row.email,
                        "phone": row.phone,
                        "is_deleted": row.deleted_at is not None,
                        "match_snippet": row.match_snippet,
                    })
            except Exception as e:
                # FTS tables might not exist yet or query error, fall back to LIKE search
                print(f"FTS client search error, falling back to LIKE: {e}", flush=True)
                results["clients"] = await SearchService._fallback_client_search(
                    session, query, limit
                )

        if search_line_items:
            try:
                # Search line items using FTS5, joining to get invoice context
                line_items_sql = text("""
                    SELECT ii.id, ii.invoice_id, ii.description, ii.quantity, ii.unit_type,
                           ii.unit_price, ii.total,
                           i.invoice_number, i.client_name, i.client_business,
                           i.status, i.currency_code, i.issue_date, i.deleted_at,
                           snippet(invoice_items_fts, 0, '<mark>', '</mark>', '...', 32) as match_snippet
                    FROM invoice_items_fts
                    JOIN invoice_items ii ON invoice_items_fts.rowid = ii.id
                    JOIN invoices i ON ii.invoice_id = i.id
                    WHERE invoice_items_fts MATCH :query
                    ORDER BY rank
                    LIMIT :limit
                """)
                result = await session.execute(line_items_sql, {"query": fts_query, "limit": limit})
                for row in result.fetchall():
                    # issue_date may be string (from raw SQL) or datetime
                    issue_date = row.issue_date
                    if issue_date and hasattr(issue_date, 'isoformat'):
                        issue_date = issue_date.isoformat()
                    results["line_items"].append({
                        "id": row.id,
                        "invoice_id": row.invoice_id,
                        "description": row.description,
                        "quantity": row.quantity,
                        "unit_type": row.unit_type,
                        "unit_price": str(row.unit_price),
                        "total": str(row.total),
                        "invoice_number": row.invoice_number,
                        "client_name": row.client_name,
                        "client_business": row.client_business,
                        "invoice_status": row.status,
                        "currency_code": row.currency_code,
                        "issue_date": issue_date,
                        "is_deleted": row.deleted_at is not None,
                        "match_snippet": row.match_snippet,
                    })
            except Exception as e:
                # FTS tables might not exist yet, fall back to LIKE search
                results["line_items"] = await SearchService._fallback_line_items_search(
                    session, query, limit
                )

        return results

    @staticmethod
    async def _fallback_invoice_search(
        session: AsyncSession, query: str, limit: int
    ) -> list:
        """Fallback LIKE-based search for invoices when FTS5 is unavailable."""
        from sqlalchemy import select, or_

        search_pattern = f"%{query}%"
        stmt = (
            select(Invoice)
            .where(
                or_(
                    Invoice.invoice_number.ilike(search_pattern),
                    Invoice.client_name.ilike(search_pattern),
                    Invoice.client_business.ilike(search_pattern),
                    Invoice.notes.ilike(search_pattern),
                )
            )
            .limit(limit)
        )
        result = await session.execute(stmt)
        invoices = result.scalars().all()
        return [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "client_name": inv.client_name,
                "client_business": inv.client_business,
                "status": inv.status,
                "total": str(inv.total),
                "currency_code": inv.currency_code,
                "issue_date": inv.issue_date.isoformat() if inv.issue_date else None,
                "is_deleted": inv.deleted_at is not None,
            }
            for inv in invoices
        ]

    @staticmethod
    async def _fallback_client_search(
        session: AsyncSession, query: str, limit: int
    ) -> list:
        """Fallback LIKE-based search for clients when FTS5 is unavailable."""
        from sqlalchemy import select, or_

        search_pattern = f"%{query}%"
        stmt = (
            select(Client)
            .where(
                or_(
                    Client.name.ilike(search_pattern),
                    Client.business_name.ilike(search_pattern),
                    Client.email.ilike(search_pattern),
                    Client.notes.ilike(search_pattern),
                )
            )
            .limit(limit)
        )
        result = await session.execute(stmt)
        clients = result.scalars().all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "business_name": c.business_name,
                "display_name": c.business_name or c.name or "Unknown",
                "email": c.email,
                "phone": c.phone,
                "is_deleted": c.deleted_at is not None,
            }
            for c in clients
        ]

    @staticmethod
    async def _fallback_line_items_search(
        session: AsyncSession, query: str, limit: int
    ) -> list:
        """Fallback LIKE-based search for line items when FTS5 is unavailable."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        search_pattern = f"%{query}%"
        stmt = (
            select(InvoiceItem)
            .where(InvoiceItem.description.ilike(search_pattern))
            .options(selectinload(InvoiceItem.invoice))
            .limit(limit)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()
        return [
            {
                "id": item.id,
                "invoice_id": item.invoice_id,
                "description": item.description,
                "quantity": item.quantity,
                "unit_type": item.unit_type,
                "unit_price": str(item.unit_price),
                "total": str(item.total),
                "invoice_number": item.invoice.invoice_number if item.invoice else None,
                "client_name": item.invoice.client_name if item.invoice else None,
                "client_business": item.invoice.client_business if item.invoice else None,
                "invoice_status": item.invoice.status if item.invoice else None,
                "currency_code": item.invoice.currency_code if item.invoice else None,
                "issue_date": item.invoice.issue_date.isoformat() if item.invoice and item.invoice.issue_date else None,
                "is_deleted": item.invoice.deleted_at is not None if item.invoice else False,
            }
            for item in items
        ]
