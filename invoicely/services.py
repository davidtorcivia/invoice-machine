"""Business logic services for invoices and clients."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

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

    # Build full address
    address_parts = [
        p
        for p in [
            client.address_line1,
            client.address_line2,
            client.city,
            client.state,
            client.postal_code,
            client.country,
        ]
        if p
    ]
    invoice.client_address = "\n".join(address_parts) if address_parts else None


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


# Settings are imported directly where needed to avoid circular imports
