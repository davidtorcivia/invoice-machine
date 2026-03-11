"""Client-related service operations."""

from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import Client, Invoice
from invoice_machine.utils import utc_now


class ClientService:
    """Service for client operations."""

    @staticmethod
    async def get_client_invoice_stats(
        session: AsyncSession,
        client_id: Optional[int] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get aggregated invoice statistics for clients in a single query."""
        from sqlalchemy import case

        total_invoiced_expr = func.coalesce(func.sum(Invoice.total), 0)
        total_paid_expr = func.coalesce(
            func.sum(case((Invoice.status == "paid", Invoice.total), else_=0)),
            0,
        )
        invoice_count_expr = func.count(Invoice.id)
        paid_invoice_count_expr = func.sum(case((Invoice.status == "paid", 1), else_=0))

        query = (
            select(
                Client.id,
                Client.name,
                Client.business_name,
                Client.email,
                total_invoiced_expr.label("total_invoiced"),
                total_paid_expr.label("total_paid"),
                invoice_count_expr.label("invoice_count"),
                paid_invoice_count_expr.label("paid_invoice_count"),
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
            .group_by(Client.id)
            .order_by(desc(total_paid_expr), Client.id)
        )

        if client_id:
            query = query.where(Client.id == client_id)

        result = await session.execute(query.limit(limit))
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
    async def get_client(session: AsyncSession, client_id: int) -> Optional[Client]:
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
    ) -> Optional[Client]:
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
