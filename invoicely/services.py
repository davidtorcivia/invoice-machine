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
from sqlalchemy import select, and_
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
    """Recalculate subtotal and total from line items."""
    result = await session.execute(
        select(InvoiceItem.total).where(InvoiceItem.invoice_id == invoice.id)
    )
    item_totals = result.scalars().all()

    subtotal = sum(Decimal(str(t)) for t in item_totals)
    invoice.subtotal = subtotal
    invoice.total = subtotal  # No tax in v1


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
    ) -> Invoice:
        """
        Create new invoice or quote.

        If client_id is provided, fetch client and snapshot info.
        Items format: [{description, quantity, unit_price, unit_type}]
        """
        from invoicely.config import get_settings
        settings = get_settings()
        business = await BusinessProfile.get_or_create(session)

        # Get client if provided
        client = None
        if client_id:
            client = await session.get(Client, client_id)

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
        unit_price = Decimal(str(unit_price))
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
    ) -> Optional[InvoiceItem]:
        """Update line item."""
        item = await session.get(InvoiceItem, item_id)
        if not item:
            return None

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
    async def remove_item(session: AsyncSession, item_id: int) -> bool:
        """Remove line item."""
        item = await session.get(InvoiceItem, item_id)
        if not item:
            return False

        invoice_id = item.invoice_id
        await session.delete(item)

        # Update invoice totals
        invoice = await session.get(Invoice, invoice_id)
        if invoice:
            await recalculate_invoice_totals(session, invoice)

        await session.commit()
        return True


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
        backup_path = self.backup_dir / backup_filename
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

        local_path = self.backup_dir / filename
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
        backup_path = self.backup_dir / backup_filename
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
