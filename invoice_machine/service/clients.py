"""Client-related service operations."""

from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import BusinessProfile, Client, Invoice
from invoice_machine.service.common import quantize_money
from invoice_machine.utils import utc_now


class ClientService:
    """Service for client operations."""

    @staticmethod
    async def get_client_invoice_stats(
        session: AsyncSession,
        client_id: int | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get aggregated invoice statistics for clients in a single query.

        Money is grouped per currency (never summed across currencies). Each
        client's headline ``total_invoiced``/``total_paid`` are reported in the
        client's dominant currency, with a full ``by_currency`` breakdown.
        """
        profile = await BusinessProfile.get(session)
        default_cur = (profile.default_currency_code if profile else None) or "USD"

        query = (
            select(
                Client.id,
                Client.name,
                Client.business_name,
                Client.email,
                Invoice.currency_code.label("currency"),
                func.coalesce(func.sum(Invoice.total), 0).label("total_invoiced"),
                func.coalesce(
                    func.sum(case((Invoice.status == "paid", Invoice.total), else_=0)), 0
                ).label("total_paid"),
                func.count(Invoice.id).label("invoice_count"),
                func.coalesce(
                    func.sum(case((Invoice.status == "paid", 1), else_=0)), 0
                ).label("paid_invoice_count"),
                func.min(Invoice.issue_date).label("first_invoice"),
                func.max(Invoice.issue_date).label("last_invoice"),
            )
            .outerjoin(
                Invoice,
                and_(
                    Invoice.client_id == Client.id,
                    Invoice.document_type == "invoice",
                    Invoice.deleted_at.is_(None),
                ),
            )
            .where(Client.deleted_at.is_(None))
            .group_by(Client.id, Invoice.currency_code)
        )

        if client_id:
            query = query.where(Client.id == client_id)

        rows = (await session.execute(query)).all()

        clients: dict[int, dict] = {}
        for row in rows:
            entry = clients.setdefault(
                row.id,
                {
                    "client_id": row.id,
                    "name": row.business_name or row.name or "Unknown",
                    "email": row.email,
                    "by_currency": {},
                    "invoice_count": 0,
                    "paid_invoice_count": 0,
                    "first_invoice": None,
                    "last_invoice": None,
                },
            )

            # Track overall first/last across all currencies.
            if row.first_invoice and (
                entry["first_invoice"] is None or row.first_invoice < entry["first_invoice"]
            ):
                entry["first_invoice"] = row.first_invoice
            if row.last_invoice and (
                entry["last_invoice"] is None or row.last_invoice > entry["last_invoice"]
            ):
                entry["last_invoice"] = row.last_invoice

            # currency is NULL only for clients with no invoices (outer join).
            if row.currency is not None:
                invoiced = quantize_money(row.total_invoiced)
                paid = quantize_money(row.total_paid)
                entry["by_currency"][row.currency] = {
                    "invoiced": str(invoiced),
                    "paid": str(paid),
                    "invoice_count": row.invoice_count or 0,
                    "paid_invoice_count": row.paid_invoice_count or 0,
                }
                entry["invoice_count"] += row.invoice_count or 0
                entry["paid_invoice_count"] += row.paid_invoice_count or 0

        for entry in clients.values():
            by_currency = entry["by_currency"]
            if by_currency:
                dominant = (
                    default_cur
                    if default_cur in by_currency
                    else max(by_currency, key=lambda c: by_currency[c]["invoice_count"])
                )
            else:
                dominant = default_cur
            entry["currency"] = dominant
            entry["total_invoiced"] = (
                Decimal(by_currency[dominant]["invoiced"]) if dominant in by_currency else Decimal("0.00")
            )
            entry["total_paid"] = (
                Decimal(by_currency[dominant]["paid"]) if dominant in by_currency else Decimal("0.00")
            )

        ordered = sorted(
            clients.values(),
            key=lambda c: (c["total_paid"], c["client_id"]),
            reverse=True,
        )
        return ordered[:limit]

    @staticmethod
    async def list_clients(
        session: AsyncSession,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> list[Client]:
        """List clients with optional soft-deleted records and search filtering."""
        query = select(Client)

        if not include_deleted:
            query = query.where(Client.deleted_at.is_(None))

        if search:
            search_term = f"%{search}%"
            query = query.where(
                (Client.name.ilike(search_term)) | (Client.business_name.ilike(search_term))
            )

        result = await session.execute(query.order_by(Client.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def get_client(session: AsyncSession, client_id: int) -> Client | None:
        """Get a client by ID."""
        return await session.get(Client, client_id)

    @staticmethod
    async def create_client(session: AsyncSession, **kwargs) -> Client:
        """Create a new client."""
        client = Client(**kwargs)
        session.add(client)
        await session.commit()
        await session.refresh(client)
        return client

    @staticmethod
    async def update_client(
        session: AsyncSession, client_id: int, **kwargs
    ) -> Client | None:
        """Update a client in place."""
        client = await ClientService.get_client(session, client_id)
        if not client:
            return None

        for key, value in kwargs.items():
            if hasattr(client, key) and value is not None:
                setattr(client, key, value)

        client.updated_at = utc_now()
        await session.commit()
        await session.refresh(client)
        return client

    @staticmethod
    async def delete_client(session: AsyncSession, client_id: int) -> bool:
        """Soft delete a client."""
        client = await ClientService.get_client(session, client_id)
        if not client:
            return False

        client.deleted_at = utc_now()
        client.updated_at = utc_now()
        await session.commit()
        return True

    @staticmethod
    async def restore_client(session: AsyncSession, client_id: int) -> bool:
        """Restore a soft-deleted client."""
        result = await session.execute(
            select(Client).where(and_(Client.id == client_id, Client.deleted_at.is_not(None)))
        )
        client = result.scalar_one_or_none()
        if not client:
            return False

        client.deleted_at = None
        client.updated_at = utc_now()
        await session.commit()
        return True
