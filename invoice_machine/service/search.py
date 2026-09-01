"""Search-related service operations."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import Client, Invoice, InvoiceItem

logger = logging.getLogger(__name__)

_INVOICES_FTS_DDL = (
    """
    CREATE VIRTUAL TABLE invoices_fts USING fts5(
        invoice_number,
        client_name,
        client_business,
        notes,
        content='invoices',
        content_rowid='id'
    )
    """,
    """
    CREATE TRIGGER invoices_fts_insert AFTER INSERT ON invoices BEGIN
        INSERT INTO invoices_fts(rowid, invoice_number, client_name, client_business, notes)
        VALUES (new.id, new.invoice_number, new.client_name, new.client_business, new.notes);
    END
    """,
    """
    CREATE TRIGGER invoices_fts_delete AFTER DELETE ON invoices BEGIN
        INSERT INTO invoices_fts(invoices_fts, rowid, invoice_number, client_name, client_business, notes)
        VALUES ('delete', old.id, old.invoice_number, old.client_name, old.client_business, old.notes);
    END
    """,
    """
    CREATE TRIGGER invoices_fts_update AFTER UPDATE ON invoices BEGIN
        INSERT INTO invoices_fts(invoices_fts, rowid, invoice_number, client_name, client_business, notes)
        VALUES ('delete', old.id, old.invoice_number, old.client_name, old.client_business, old.notes);
        INSERT INTO invoices_fts(rowid, invoice_number, client_name, client_business, notes)
        VALUES (new.id, new.invoice_number, new.client_name, new.client_business, new.notes);
    END
    """,
)

_CLIENTS_FTS_DDL = (
    """
    CREATE VIRTUAL TABLE clients_fts USING fts5(
        name,
        business_name,
        email,
        notes,
        content='clients',
        content_rowid='id'
    )
    """,
    """
    CREATE TRIGGER clients_fts_insert AFTER INSERT ON clients BEGIN
        INSERT INTO clients_fts(rowid, name, business_name, email, notes)
        VALUES (new.id, new.name, new.business_name, new.email, new.notes);
    END
    """,
    """
    CREATE TRIGGER clients_fts_delete AFTER DELETE ON clients BEGIN
        INSERT INTO clients_fts(clients_fts, rowid, name, business_name, email, notes)
        VALUES ('delete', old.id, old.name, old.business_name, old.email, old.notes);
    END
    """,
    """
    CREATE TRIGGER clients_fts_update AFTER UPDATE ON clients BEGIN
        INSERT INTO clients_fts(clients_fts, rowid, name, business_name, email, notes)
        VALUES ('delete', old.id, old.name, old.business_name, old.email, old.notes);
        INSERT INTO clients_fts(rowid, name, business_name, email, notes)
        VALUES (new.id, new.name, new.business_name, new.email, new.notes);
    END
    """,
)

_ITEMS_FTS_STAGING_DDL = "CREATE VIRTUAL TABLE invoice_items_fts_new USING fts5(description)"
_ITEMS_FTS_POPULATE = """
    INSERT INTO invoice_items_fts_new(rowid, description)
    SELECT id, description FROM invoice_items
"""
_ITEMS_FTS_TRIGGER_DDL = (
    """
    CREATE TRIGGER invoice_items_fts_insert AFTER INSERT ON invoice_items BEGIN
        INSERT INTO invoice_items_fts(rowid, description)
        VALUES (new.id, new.description);
    END
    """,
    """
    CREATE TRIGGER invoice_items_fts_delete AFTER DELETE ON invoice_items BEGIN
        DELETE FROM invoice_items_fts WHERE rowid = old.id;
    END
    """,
    """
    CREATE TRIGGER invoice_items_fts_update AFTER UPDATE ON invoice_items BEGIN
        DELETE FROM invoice_items_fts WHERE rowid = old.id;
        INSERT INTO invoice_items_fts(rowid, description)
        VALUES (new.id, new.description);
    END
    """,
)

_ITEM_FTS_TRIGGER_NAMES = (
    "invoice_items_fts_insert",
    "invoice_items_fts_delete",
    "invoice_items_fts_update",
)

_INVOICE_FTS_SEARCH_SQL = """
    SELECT i.id, i.invoice_number, i.client_name, i.client_business,
           i.status, i.total, i.currency_code, i.issue_date, i.deleted_at,
           snippet(invoices_fts, 0, '<mark>', '</mark>', '...', 32) as match_snippet
    FROM invoices_fts
    JOIN invoices i ON invoices_fts.rowid = i.id
    WHERE invoices_fts MATCH :query
    ORDER BY rank
    LIMIT :limit
"""

_CLIENT_FTS_SEARCH_SQL = """
    SELECT c.id, c.name, c.business_name, c.email, c.phone, c.deleted_at,
           snippet(clients_fts, 0, '<mark>', '</mark>', '...', 32) as match_snippet
    FROM clients_fts
    JOIN clients c ON clients_fts.rowid = c.id
    WHERE clients_fts MATCH :query
    ORDER BY rank
    LIMIT :limit
"""

_LINE_ITEM_FTS_SEARCH_SQL = """
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


def _like_pattern(query: str) -> str:
    """Build a contains-pattern with LIKE wildcards escaped.

    Without this, a search for "100%" or "a_b" leaks SQL wildcards into the
    pattern and matches far more than the user asked for.
    """
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _iso_or_none(value):
    return value.isoformat() if value and hasattr(value, "isoformat") else value


def _normalize_fts_query(query: str) -> str | None:
    """Strip FTS5 operators/syntax from user input and return a prefix query."""
    safe_query = query.strip()
    for char in ['"', "*", "-", "(", ")", ":", "^"]:
        safe_query = safe_query.replace(char, " ")
    for op in [" AND ", " OR ", " NOT ", " NEAR "]:
        safe_query = safe_query.replace(op, " ")
        safe_query = safe_query.replace(op.lower(), " ")
    safe_query = " ".join(safe_query.split())
    if not safe_query:
        return None
    return " ".join(f"{word}*" for word in safe_query.split())


async def _existing_names(session, kind: str, names: tuple[str, ...]) -> set[str]:
    from sqlalchemy import text

    placeholders = ", ".join(f":n{i}" for i in range(len(names)))
    rows = await session.execute(
        text(f"SELECT name FROM sqlite_master WHERE type=:kind AND name IN ({placeholders})"),
        {"kind": kind, **{f"n{i}": name for i, name in enumerate(names)}},
    )
    return {row[0] for row in rows.fetchall()}


async def _table_counts(session) -> tuple[int, int, int]:
    from sqlalchemy import text

    counts = []
    for table in ("invoices", "clients", "invoice_items"):
        counts.append((await session.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar())
    return counts[0], counts[1], counts[2]


async def _fts_up_to_date(session, invoices: int, clients: int, line_items: int) -> bool:
    """Whether every FTS table's row count already matches its base table."""
    from sqlalchemy import text

    try:
        for table, expected in (
            ("invoices_fts", invoices),
            ("clients_fts", clients),
            ("invoice_items_fts", line_items),
        ):
            actual = (await session.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar()
            if actual != expected:
                return False
        return True
    except Exception:
        return False


_ALREADY_INDEXED = "FTS indexes already up to date"


async def _reindex_precheck(session, force: bool) -> tuple[str | None, tuple, set[str]]:
    """Return (skip reason or None, base-table counts, existing FTS table names)."""
    base_tables = await _existing_names(session, "table", ("invoices", "clients", "invoice_items"))
    if "invoices" not in base_tables or "clients" not in base_tables:
        return "Base tables don't exist", (0, 0, 0), set()

    existing_fts_tables = await _existing_names(
        session, "table", ("invoices_fts", "clients_fts", "invoice_items_fts")
    )
    # The invoice_items FTS sync triggers can be silently dropped when SQLite
    # rebuilds invoice_items (e.g. a batch_alter migration). Row counts can still
    # match right afterwards, so also require the triggers to exist before
    # declaring the index up to date.
    item_triggers_present = set(_ITEM_FTS_TRIGGER_NAMES) <= await _existing_names(
        session, "trigger", _ITEM_FTS_TRIGGER_NAMES
    )

    counts = await _table_counts(session)
    if counts == (0, 0, 0):
        return "No data to index", counts, existing_fts_tables

    if (
        not force
        and {"invoices_fts", "clients_fts", "invoice_items_fts"} <= existing_fts_tables
        and item_triggers_present
        and await _fts_up_to_date(session, *counts)
    ):
        return _ALREADY_INDEXED, counts, existing_fts_tables
    return None, counts, existing_fts_tables


async def _create_content_fts(session, statements: tuple[str, ...]) -> None:
    from sqlalchemy import text

    for statement in statements:
        await session.execute(text(statement))
    await session.commit()


async def _rebuild_item_fts(session, line_items_count: int) -> None:
    """Recreate invoice_items_fts through a staging table.

    SQLite DDL autocommits, so a DROP cannot be rolled back: the new table must
    be fully built before the old one is dropped, or a failed populate would
    leave line-item search permanently on the LIKE fallback.
    """
    from sqlalchemy import text

    await session.execute(text("DROP TABLE IF EXISTS invoice_items_fts_new"))
    await session.execute(text(_ITEMS_FTS_STAGING_DDL))
    if line_items_count > 0:
        await session.execute(text(_ITEMS_FTS_POPULATE))
        await session.commit()

    for trigger in _ITEM_FTS_TRIGGER_NAMES:
        await session.execute(text(f"DROP TRIGGER IF EXISTS {trigger}"))
    await session.execute(text("DROP TABLE IF EXISTS invoice_items_fts"))
    await session.execute(text("ALTER TABLE invoice_items_fts_new RENAME TO invoice_items_fts"))
    for statement in _ITEMS_FTS_TRIGGER_DDL:
        await session.execute(text(statement))
    await session.commit()


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
            skip_reason, counts, existing_fts_tables = await _reindex_precheck(session, force)
            if skip_reason is not None:
                result["skipped"] = True
                result["reason"] = skip_reason
                if skip_reason == _ALREADY_INDEXED:
                    result["invoices_indexed"], result["clients_indexed"] = counts[0], counts[1]
                    result["line_items_indexed"] = counts[2]
                return result
            invoices_count, clients_count, line_items_count = counts

            if "invoices_fts" not in existing_fts_tables:
                await _create_content_fts(session, _INVOICES_FTS_DDL)
            if "clients_fts" not in existing_fts_tables:
                await _create_content_fts(session, _CLIENTS_FTS_DDL)

            await _rebuild_item_fts(session, line_items_count)
            if line_items_count > 0:
                result["line_items_indexed"] = line_items_count

            if invoices_count > 0:
                await session.execute(
                    text("INSERT INTO invoices_fts(invoices_fts) VALUES('rebuild')")
                )
                result["invoices_indexed"] = invoices_count
            if clients_count > 0:
                await session.execute(
                    text("INSERT INTO clients_fts(clients_fts) VALUES('rebuild')")
                )
                result["clients_indexed"] = clients_count

            await session.commit()
            result["rebuilt"] = True
            return result
        except Exception as exc:
            await session.rollback()
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
        results = {"invoices": [], "clients": [], "line_items": []}
        limit = max(1, min(limit, 100))

        if not query or not query.strip():
            return results

        fts_query = _normalize_fts_query(query)
        if fts_query is None:
            return results

        wanted = (
            ("invoices", search_invoices, SearchService._fts_invoice_search),
            ("clients", search_clients, SearchService._fts_client_search),
            ("line_items", search_line_items, SearchService._fts_line_items_search),
        )
        for key, enabled, fts_search in wanted:
            if enabled:
                results[key] = await fts_search(session, fts_query, query, limit)
        return results

    @staticmethod
    async def _fts_rows(session: AsyncSession, sql: str, fts_query: str, limit: int) -> list:
        from sqlalchemy import text

        result = await session.execute(text(sql), {"query": fts_query, "limit": limit})
        return result.fetchall()

    @staticmethod
    async def _fts_invoice_search(
        session: AsyncSession, fts_query: str, query: str, limit: int
    ) -> list:
        try:
            rows = await SearchService._fts_rows(session, _INVOICE_FTS_SEARCH_SQL, fts_query, limit)
        except Exception:
            logger.warning(
                "FTS unavailable for invoice search; falling back to a LIKE scan. "
                "Run a reindex if this persists.",
                exc_info=True,
            )
            return await SearchService._fallback_invoice_search(session, query, limit)
        return [
            {
                "id": row.id,
                "invoice_number": row.invoice_number,
                "client_name": row.client_name,
                "client_business": row.client_business,
                "status": row.status,
                "total": str(row.total),
                "currency_code": row.currency_code,
                "issue_date": _iso_or_none(row.issue_date),
                "is_deleted": row.deleted_at is not None,
                "match_snippet": row.match_snippet,
            }
            for row in rows
        ]

    @staticmethod
    async def _fts_client_search(
        session: AsyncSession, fts_query: str, query: str, limit: int
    ) -> list:
        try:
            rows = await SearchService._fts_rows(session, _CLIENT_FTS_SEARCH_SQL, fts_query, limit)
        except Exception:
            logger.warning(
                "FTS unavailable for client search; falling back to a LIKE scan. "
                "Run a reindex if this persists.",
                exc_info=True,
            )
            return await SearchService._fallback_client_search(session, query, limit)
        return [
            {
                "id": row.id,
                "name": row.name,
                "business_name": row.business_name,
                "display_name": row.business_name or row.name or "Unknown",
                "email": row.email,
                "phone": row.phone,
                "is_deleted": row.deleted_at is not None,
                "match_snippet": row.match_snippet,
            }
            for row in rows
        ]

    @staticmethod
    async def _fts_line_items_search(
        session: AsyncSession, fts_query: str, query: str, limit: int
    ) -> list:
        try:
            rows = await SearchService._fts_rows(
                session, _LINE_ITEM_FTS_SEARCH_SQL, fts_query, limit
            )
        except Exception:
            logger.warning(
                "FTS unavailable for line_items search; falling back to a LIKE scan. "
                "Run a reindex if this persists.",
                exc_info=True,
            )
            return await SearchService._fallback_line_items_search(session, query, limit)
        return [
            {
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
                "issue_date": _iso_or_none(row.issue_date),
                "is_deleted": row.deleted_at is not None,
            }
            for row in rows
        ]

    @staticmethod
    async def _fallback_invoice_search(session: AsyncSession, query: str, limit: int) -> list:
        """Fallback LIKE-based search for invoices when FTS5 is unavailable."""
        from sqlalchemy import or_, select

        term = _like_pattern(query)
        result = await session.execute(
            select(Invoice)
            .where(
                or_(
                    Invoice.invoice_number.ilike(term, escape="\\"),
                    Invoice.client_name.ilike(term, escape="\\"),
                    Invoice.client_business.ilike(term, escape="\\"),
                    Invoice.notes.ilike(term, escape="\\"),
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
    async def _fallback_client_search(session: AsyncSession, query: str, limit: int) -> list:
        """Fallback LIKE-based search for clients when FTS5 is unavailable."""
        from sqlalchemy import or_, select

        term = _like_pattern(query)
        result = await session.execute(
            select(Client)
            .where(
                or_(
                    Client.name.ilike(term, escape="\\"),
                    Client.business_name.ilike(term, escape="\\"),
                    Client.email.ilike(term, escape="\\"),
                    Client.notes.ilike(term, escape="\\"),
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
    async def _fallback_line_items_search(session: AsyncSession, query: str, limit: int) -> list:
        """Fallback LIKE-based search for line items when FTS5 is unavailable."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await session.execute(
            select(InvoiceItem)
            .where(InvoiceItem.description.ilike(_like_pattern(query), escape="\\"))
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
