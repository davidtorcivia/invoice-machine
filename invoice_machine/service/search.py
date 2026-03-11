"""Search-related service operations."""

from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import Client, Invoice, InvoiceItem


class SearchService:
    """Service for full-text search across invoices and clients."""

    @staticmethod
    async def reindex_fts(session: AsyncSession, force: bool = False) -> dict:
        """Rebuild FTS tables from main tables using the FTS5 rebuild command."""
        from sqlalchemy import text

        result = {
            "invoices_indexed": 0,
            "clients_indexed": 0,
            "line_items_indexed": 0,
            "skipped": False,
            "rebuilt": False,
        }

        try:
            base_tables_check = await session.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('invoices', 'clients', 'invoice_items')"
                )
            )
            base_tables = {row[0] for row in base_tables_check.fetchall()}
            if "invoices" not in base_tables or "clients" not in base_tables:
                result["skipped"] = True
                result["reason"] = "Base tables don't exist"
                return result

            fts_tables_check = await session.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('invoices_fts', 'clients_fts', 'invoice_items_fts')"
                )
            )
            existing_fts_tables = {row[0] for row in fts_tables_check.fetchall()}

            invoices_count = (await session.execute(text("SELECT COUNT(*) FROM invoices"))).scalar()
            clients_count = (await session.execute(text("SELECT COUNT(*) FROM clients"))).scalar()
            line_items_count = (
                await session.execute(text("SELECT COUNT(*) FROM invoice_items"))
            ).scalar()

            if invoices_count == 0 and clients_count == 0 and line_items_count == 0:
                result["skipped"] = True
                result["reason"] = "No data to index"
                return result

            if (
                not force
                and {"invoices_fts", "clients_fts", "invoice_items_fts"} <= existing_fts_tables
            ):
                try:
                    invoices_fts_count = (
                        await session.execute(text("SELECT COUNT(*) FROM invoices_fts"))
                    ).scalar()
                    clients_fts_count = (
                        await session.execute(text("SELECT COUNT(*) FROM clients_fts"))
                    ).scalar()
                    line_items_fts_count = (
                        await session.execute(text("SELECT COUNT(*) FROM invoice_items_fts"))
                    ).scalar()

                    if (
                        invoices_count == invoices_fts_count
                        and clients_count == clients_fts_count
                        and line_items_count == line_items_fts_count
                    ):
                        result["invoices_indexed"] = invoices_count
                        result["clients_indexed"] = clients_count
                        result["line_items_indexed"] = line_items_count
                        result["skipped"] = True
                        result["reason"] = "FTS indexes already up to date"
                        return result
                except Exception:
                    pass

            if "invoices_fts" not in existing_fts_tables:
                await session.execute(
                    text(
                        """
                    CREATE VIRTUAL TABLE invoices_fts USING fts5(
                        invoice_number,
                        client_name,
                        client_business,
                        notes,
                        content='invoices',
                        content_rowid='id'
                    )
                    """
                    )
                )
                await session.execute(
                    text(
                        """
                    CREATE TRIGGER invoices_fts_insert AFTER INSERT ON invoices BEGIN
                        INSERT INTO invoices_fts(rowid, invoice_number, client_name, client_business, notes)
                        VALUES (new.id, new.invoice_number, new.client_name, new.client_business, new.notes);
                    END
                    """
                    )
                )
                await session.execute(
                    text(
                        """
                    CREATE TRIGGER invoices_fts_delete AFTER DELETE ON invoices BEGIN
                        INSERT INTO invoices_fts(invoices_fts, rowid, invoice_number, client_name, client_business, notes)
                        VALUES ('delete', old.id, old.invoice_number, old.client_name, old.client_business, old.notes);
                    END
                    """
                    )
                )
                await session.execute(
                    text(
                        """
                    CREATE TRIGGER invoices_fts_update AFTER UPDATE ON invoices BEGIN
                        INSERT INTO invoices_fts(invoices_fts, rowid, invoice_number, client_name, client_business, notes)
                        VALUES ('delete', old.id, old.invoice_number, old.client_name, old.client_business, old.notes);
                        INSERT INTO invoices_fts(rowid, invoice_number, client_name, client_business, notes)
                        VALUES (new.id, new.invoice_number, new.client_name, new.client_business, new.notes);
                    END
                    """
                    )
                )
                await session.commit()

            if "clients_fts" not in existing_fts_tables:
                await session.execute(
                    text(
                        """
                    CREATE VIRTUAL TABLE clients_fts USING fts5(
                        name,
                        business_name,
                        email,
                        notes,
                        content='clients',
                        content_rowid='id'
                    )
                    """
                    )
                )
                await session.execute(
                    text(
                        """
                    CREATE TRIGGER clients_fts_insert AFTER INSERT ON clients BEGIN
                        INSERT INTO clients_fts(rowid, name, business_name, email, notes)
                        VALUES (new.id, new.name, new.business_name, new.email, new.notes);
                    END
                    """
                    )
                )
                await session.execute(
                    text(
                        """
                    CREATE TRIGGER clients_fts_delete AFTER DELETE ON clients BEGIN
                        INSERT INTO clients_fts(clients_fts, rowid, name, business_name, email, notes)
                        VALUES ('delete', old.id, old.name, old.business_name, old.email, old.notes);
                    END
                    """
                    )
                )
                await session.execute(
                    text(
                        """
                    CREATE TRIGGER clients_fts_update AFTER UPDATE ON clients BEGIN
                        INSERT INTO clients_fts(clients_fts, rowid, name, business_name, email, notes)
                        VALUES ('delete', old.id, old.name, old.business_name, old.email, old.notes);
                        INSERT INTO clients_fts(rowid, name, business_name, email, notes)
                        VALUES (new.id, new.name, new.business_name, new.email, new.notes);
                    END
                    """
                    )
                )
                await session.commit()

            await session.execute(text("DROP TABLE IF EXISTS invoice_items_fts"))
            await session.execute(text("DROP TRIGGER IF EXISTS invoice_items_fts_insert"))
            await session.execute(text("DROP TRIGGER IF EXISTS invoice_items_fts_delete"))
            await session.execute(text("DROP TRIGGER IF EXISTS invoice_items_fts_update"))

            await session.execute(
                text(
                    """
                CREATE VIRTUAL TABLE invoice_items_fts USING fts5(
                    description
                )
                """
                )
            )
            await session.execute(
                text(
                    """
                CREATE TRIGGER invoice_items_fts_insert AFTER INSERT ON invoice_items BEGIN
                    INSERT INTO invoice_items_fts(rowid, description)
                    VALUES (new.id, new.description);
                END
                """
                )
            )
            await session.execute(
                text(
                    """
                CREATE TRIGGER invoice_items_fts_delete AFTER DELETE ON invoice_items BEGIN
                    DELETE FROM invoice_items_fts WHERE rowid = old.id;
                END
                """
                )
            )
            await session.execute(
                text(
                    """
                CREATE TRIGGER invoice_items_fts_update AFTER UPDATE ON invoice_items BEGIN
                    DELETE FROM invoice_items_fts WHERE rowid = old.id;
                    INSERT INTO invoice_items_fts(rowid, description)
                    VALUES (new.id, new.description);
                END
                """
                )
            )
            await session.commit()

            if invoices_count > 0:
                await session.execute(text("INSERT INTO invoices_fts(invoices_fts) VALUES('rebuild')"))
                result["invoices_indexed"] = invoices_count

            if clients_count > 0:
                await session.execute(text("INSERT INTO clients_fts(clients_fts) VALUES('rebuild')"))
                result["clients_indexed"] = clients_count

            if line_items_count > 0:
                await session.execute(
                    text(
                        """
                    INSERT INTO invoice_items_fts(rowid, description)
                    SELECT id, description FROM invoice_items
                    """
                    )
                )
                result["line_items_indexed"] = line_items_count

            await session.commit()
            result["rebuilt"] = True
            return result
        except Exception as exc:
            result["error"] = str(exc)
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
        """Search invoices, clients, and line items using FTS with LIKE fallbacks."""
        from sqlalchemy import text

        results = {"invoices": [], "clients": [], "line_items": []}
        limit = max(1, min(limit, 100))

        if not query or not query.strip():
            return results

        safe_query = query.strip()
        for char in ['"', "*", "-", "(", ")", ":", "^"]:
            safe_query = safe_query.replace(char, " ")
        for op in [" AND ", " OR ", " NOT ", " NEAR "]:
            safe_query = safe_query.replace(op, " ")
            safe_query = safe_query.replace(op.lower(), " ")
        safe_query = " ".join(safe_query.split())
        if not safe_query:
            return results

        fts_query = " ".join(f"{word}*" for word in safe_query.split())

        if search_invoices:
            try:
                result = await session.execute(
                    text(
                        """
                    SELECT i.id, i.invoice_number, i.client_name, i.client_business,
                           i.status, i.total, i.currency_code, i.issue_date, i.deleted_at,
                           snippet(invoices_fts, 0, '<mark>', '</mark>', '...', 32) as match_snippet
                    FROM invoices_fts
                    JOIN invoices i ON invoices_fts.rowid = i.id
                    WHERE invoices_fts MATCH :query
                    ORDER BY rank
                    LIMIT :limit
                    """
                    ),
                    {"query": fts_query, "limit": limit},
                )
                for row in result.fetchall():
                    issue_date = row.issue_date
                    if issue_date and hasattr(issue_date, "isoformat"):
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
            except Exception:
                results["invoices"] = await SearchService._fallback_invoice_search(
                    session, query, limit
                )

        if search_clients:
            try:
                result = await session.execute(
                    text(
                        """
                    SELECT c.id, c.name, c.business_name, c.email, c.phone, c.deleted_at,
                           snippet(clients_fts, 0, '<mark>', '</mark>', '...', 32) as match_snippet
                    FROM clients_fts
                    JOIN clients c ON clients_fts.rowid = c.id
                    WHERE clients_fts MATCH :query
                    ORDER BY rank
                    LIMIT :limit
                    """
                    ),
                    {"query": fts_query, "limit": limit},
                )
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
            except Exception:
                results["clients"] = await SearchService._fallback_client_search(
                    session, query, limit
                )

        if search_line_items:
            try:
                result = await session.execute(
                    text(
                        """
                    SELECT ii.id, ii.invoice_id, ii.description, ii.quantity, ii.unit_type,
                           ii.unit_price, ii.total,
                           i.invoice_number, i.client_name, i.client_business,
                           i.status, i.currency_code, i.issue_date, i.deleted_at
                    FROM invoice_items_fts
                    JOIN invoice_items ii ON invoice_items_fts.rowid = ii.id
                    JOIN invoices i ON ii.invoice_id = i.id
                    WHERE invoice_items_fts MATCH :query
                    ORDER BY rank
                    LIMIT :limit
                    """
                    ),
                    {"query": fts_query, "limit": limit},
                )
                for row in result.fetchall():
                    issue_date = row.issue_date
                    if issue_date and hasattr(issue_date, "isoformat"):
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
                    })
            except Exception:
                results["line_items"] = await SearchService._fallback_line_items_search(
                    session, query, limit
                )

        return results

    @staticmethod
    async def _fallback_invoice_search(
        session: AsyncSession, query: str, limit: int
    ) -> list:
        """Fallback LIKE-based search for invoices when FTS5 is unavailable."""
        from sqlalchemy import or_, select

        result = await session.execute(
            select(Invoice)
            .where(
                or_(
                    Invoice.invoice_number.ilike(f"%{query}%"),
                    Invoice.client_name.ilike(f"%{query}%"),
                    Invoice.client_business.ilike(f"%{query}%"),
                    Invoice.notes.ilike(f"%{query}%"),
                )
            )
            .limit(limit)
        )
        return [
            {
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "client_name": invoice.client_name,
                "client_business": invoice.client_business,
                "status": invoice.status,
                "total": str(invoice.total),
                "currency_code": invoice.currency_code,
                "issue_date": invoice.issue_date.isoformat() if invoice.issue_date else None,
                "is_deleted": invoice.deleted_at is not None,
            }
            for invoice in result.scalars().all()
        ]

    @staticmethod
    async def _fallback_client_search(
        session: AsyncSession, query: str, limit: int
    ) -> list:
        """Fallback LIKE-based search for clients when FTS5 is unavailable."""
        from sqlalchemy import or_, select

        result = await session.execute(
            select(Client)
            .where(
                or_(
                    Client.name.ilike(f"%{query}%"),
                    Client.business_name.ilike(f"%{query}%"),
                    Client.email.ilike(f"%{query}%"),
                    Client.notes.ilike(f"%{query}%"),
                )
            )
            .limit(limit)
        )
        return [
            {
                "id": client.id,
                "name": client.name,
                "business_name": client.business_name,
                "display_name": client.business_name or client.name or "Unknown",
                "email": client.email,
                "phone": client.phone,
                "is_deleted": client.deleted_at is not None,
            }
            for client in result.scalars().all()
        ]

    @staticmethod
    async def _fallback_line_items_search(
        session: AsyncSession, query: str, limit: int
    ) -> list:
        """Fallback LIKE-based search for line items when FTS5 is unavailable."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await session.execute(
            select(InvoiceItem)
            .where(InvoiceItem.description.ilike(f"%{query}%"))
            .options(selectinload(InvoiceItem.invoice))
            .limit(limit)
        )
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
                "issue_date": item.invoice.issue_date.isoformat()
                if item.invoice and item.invoice.issue_date
                else None,
                "is_deleted": item.invoice.deleted_at is not None if item.invoice else False,
            }
            for item in result.scalars().all()
        ]
