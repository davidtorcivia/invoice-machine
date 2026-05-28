"""Invoice-related service operations."""

from datetime import date
from decimal import Decimal

from sqlalchemy import and_, asc, desc, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import BusinessProfile, Client, Invoice, InvoiceItem
from invoice_machine.service.common import (
    calculate_due_date,
    generate_invoice_number,
    is_auto_invoice_number,
    line_item_total,
    recalculate_invoice_totals,
    snapshot_client_info,
)
from invoice_machine.utils import normalize_invoice_number_override, utc_now

# How many times to retry invoice-number allocation under a concurrent-create race.
_NUMBER_ALLOCATION_ATTEMPTS = 6


def _coerce_quantity(value) -> int:
    """Coerce a line-item quantity to a positive int (tolerant of str/float input)."""
    try:
        qty = int(Decimal(str(value)))
    except (ArithmeticError, ValueError, TypeError):
        raise ValueError("Quantity must be a number") from None
    if qty < 1:
        raise ValueError("Quantity must be at least 1")
    return qty


class InvoiceService:
    """Service for invoice operations."""

    @staticmethod
    async def list_invoices(
        session: AsyncSession,
        status: str | None = None,
        document_type: str | None = None,
        client_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        include_deleted: bool = False,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Invoice]:
        """List invoices with filters, sorting, and pagination controls."""
        query = select(Invoice)

        if not include_deleted:
            query = query.where(Invoice.deleted_at.is_(None))
        if status:
            query = query.where(Invoice.status == status)
        if document_type:
            query = query.where(Invoice.document_type == document_type)
        if client_id:
            query = query.where(Invoice.client_id == client_id)
        if from_date:
            query = query.where(Invoice.issue_date >= from_date)
        if to_date:
            query = query.where(Invoice.issue_date <= to_date)

        sort_columns = {
            "created_at": Invoice.created_at,
            "issue_date": Invoice.issue_date,
            "due_date": Invoice.due_date,
            "invoice_number": Invoice.invoice_number,
            "total": Invoice.total,
            "status": Invoice.status,
            "client": func.coalesce(Invoice.client_business, Invoice.client_name, ""),
        }
        sort_column = sort_columns.get((sort_by or "").lower(), Invoice.created_at)
        order_expr = asc(sort_column) if (sort_dir or "").lower() == "asc" else desc(sort_column)

        safe_limit = max(1, min(int(limit), 500))
        safe_offset = max(0, int(offset))

        result = await session.execute(
            query.order_by(order_expr, Invoice.id.desc()).offset(safe_offset).limit(safe_limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_invoices_paginated(
        session: AsyncSession,
        status: str | None = None,
        document_type: str | None = None,
        client_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        include_deleted: bool = False,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        page: int = 1,
        per_page: int = 25,
    ) -> tuple[list[Invoice], int]:
        """List invoices with pagination metadata."""
        conditions = []
        if not include_deleted:
            conditions.append(Invoice.deleted_at.is_(None))
        if status:
            conditions.append(Invoice.status == status)
        if document_type:
            conditions.append(Invoice.document_type == document_type)
        if client_id:
            conditions.append(Invoice.client_id == client_id)
        if from_date:
            conditions.append(Invoice.issue_date >= from_date)
        if to_date:
            conditions.append(Invoice.issue_date <= to_date)

        count_query = select(func.count(Invoice.id))
        if conditions:
            count_query = count_query.where(*conditions)
        total = int((await session.execute(count_query)).scalar() or 0)

        safe_page = max(1, int(page))
        safe_per_page = max(1, min(int(per_page), 100))
        offset = (safe_page - 1) * safe_per_page

        invoices = await InvoiceService.list_invoices(
            session,
            status=status,
            document_type=document_type,
            client_id=client_id,
            from_date=from_date,
            to_date=to_date,
            include_deleted=include_deleted,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=safe_per_page,
            offset=offset,
        )
        return invoices, total

    @staticmethod
    async def get_invoice(session: AsyncSession, invoice_id: int) -> Invoice | None:
        """Get an invoice by ID."""
        return await session.get(Invoice, invoice_id)

    @staticmethod
    async def create_invoice(
        session: AsyncSession,
        client_id: int | None = None,
        issue_date: date | None = None,
        due_date: date | None = None,
        payment_terms_days: int | None = None,
        currency_code: str = "USD",
        notes: str | None = None,
        items: list[dict] | None = None,
        document_type: str = "invoice",
        client_reference: str | None = None,
        show_payment_instructions: bool = True,
        selected_payment_methods: str | None = None,
        invoice_number_override: str | None = None,
        tax_enabled: bool | None = None,
        tax_rate: Decimal | None = None,
        tax_name: str | None = None,
    ) -> Invoice:
        """Create a new invoice or quote, including optional line items."""
        business = await BusinessProfile.get_or_create(session)

        if tax_rate is not None and (tax_rate < 0 or tax_rate > 100):
            raise ValueError("Tax rate must be between 0 and 100")

        client = await session.get(Client, client_id) if client_id else None

        if tax_enabled is not None:
            use_tax_enabled = tax_enabled
        elif client and client.tax_enabled is not None:
            use_tax_enabled = bool(client.tax_enabled)
        else:
            use_tax_enabled = bool(business.default_tax_enabled)

        if tax_rate is not None:
            use_tax_rate = tax_rate
        elif client and client.tax_rate is not None:
            use_tax_rate = client.tax_rate
        else:
            use_tax_rate = business.default_tax_rate

        if tax_name is not None:
            use_tax_name = tax_name
        elif client and client.tax_name is not None:
            use_tax_name = client.tax_name
        else:
            use_tax_name = business.default_tax_name

        invoice_date = issue_date or utc_now().date()

        # Validate/normalize line items up front so a failure doesn't leave a
        # half-built invoice, and so string/float quantities (e.g. from MCP) are
        # coerced rather than crashing mid-build.
        valid_unit_types = {"qty", "hours"}
        normalized_items: list[dict] = []
        for index, item_data in enumerate(items or []):
            quantity = _coerce_quantity(item_data.get("quantity", 1))
            unit_price = Decimal(str(item_data.get("unit_price", 0)))
            if unit_price < 0:
                raise ValueError("Unit price cannot be negative")
            unit_type = item_data.get("unit_type", "qty")
            if unit_type not in valid_unit_types:
                raise ValueError(f"Invalid unit type. Must be one of: {sorted(valid_unit_types)}")
            normalized_items.append(
                {
                    "description": item_data.get("description", ""),
                    "quantity": quantity,
                    "unit_type": unit_type,
                    "unit_price": unit_price,
                    "total": line_item_total(unit_price, quantity),
                    "sort_order": item_data.get("sort_order", index),
                }
            )

        calculated_due_date = calculate_due_date(
            invoice_date, payment_terms_days, due_date, client, business
        )
        resolved_terms = (
            payment_terms_days
            or (client.payment_terms_days if client else None)
            or business.default_payment_terms_days
        )

        override = invoice_number_override is not None
        override_number = (
            normalize_invoice_number_override(invoice_number_override) if override else None
        )
        attempts = 1 if override else _NUMBER_ALLOCATION_ATTEMPTS
        last_error: IntegrityError | None = None

        # Retry loop guards against the read-max-then-+1 numbering race: if a
        # concurrent create grabs the same number, the unique constraint fires
        # and we regenerate instead of returning a 500.
        for _attempt in range(attempts):
            invoice_number = override_number or await generate_invoice_number(
                session, invoice_date, document_type
            )
            invoice = Invoice(
                invoice_number=invoice_number,
                client_id=client_id,
                issue_date=invoice_date,
                due_date=calculated_due_date,
                payment_terms_days=resolved_terms,
                currency_code=currency_code,
                notes=notes,
                status="draft",
                document_type=document_type,
                client_reference=client_reference,
                show_payment_instructions=1 if show_payment_instructions else 0,
                selected_payment_methods=selected_payment_methods,
                tax_enabled=1 if use_tax_enabled else 0,
                tax_rate=use_tax_rate or Decimal("0.00"),
                tax_name=use_tax_name or "Tax",
            )
            if client:
                await snapshot_client_info(session, client, invoice)

            session.add(invoice)
            try:
                await session.flush()
                if normalized_items:
                    session.add_all(
                        InvoiceItem(invoice_id=invoice.id, **item) for item in normalized_items
                    )
                    await session.flush()
                await recalculate_invoice_totals(session, invoice)
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                last_error = exc
                if override:
                    raise ValueError(
                        f"Invoice number '{override_number}' already exists"
                    ) from exc
                # Re-resolve objects expired by the rollback before retrying.
                business = await BusinessProfile.get_or_create(session)
                client = await session.get(Client, client_id) if client_id else None
                continue

            await session.refresh(invoice)
            return invoice

        raise ValueError(
            "Could not allocate a unique invoice number; please retry"
        ) from last_error

    @staticmethod
    async def update_invoice(
        session: AsyncSession,
        invoice_id: int,
        issue_date: date | None = None,
        due_date: date | None = None,
        status: str | None = None,
        notes: str | None = None,
        **kwargs,
    ) -> Invoice | None:
        """Update an invoice."""
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            return None

        business = await BusinessProfile.get_or_create(session)
        client = await session.get(Client, invoice.client_id) if invoice.client_id else None

        # Only these fields may be set via **kwargs. Computed money fields
        # (subtotal/tax_amount/total) and identity fields are intentionally
        # excluded so callers cannot desync totals from line items.
        allowed_kwargs = {
            "currency_code",
            "payment_terms_days",
            "client_reference",
            "show_payment_instructions",
            "selected_payment_methods",
            "tax_enabled",
            "tax_rate",
            "tax_name",
            "document_type",
            "client_id",
        }

        tax_fields_changed = False
        doc_type_changed = False
        for key, value in kwargs.items():
            if key == "invoice_number" and value is not None:
                # Explicit custom number; normalize and treat as an override.
                invoice.invoice_number = normalize_invoice_number_override(str(value))
                continue
            if key not in allowed_kwargs or value is None:
                continue
            if key in ("tax_enabled", "tax_rate") and getattr(invoice, key) != value:
                tax_fields_changed = True
            if key == "document_type" and value != invoice.document_type:
                doc_type_changed = True
            setattr(invoice, key, value)

        date_changed = bool(issue_date and issue_date != invoice.issue_date)
        if date_changed:
            invoice.issue_date = issue_date
            if not due_date:
                invoice.due_date = calculate_due_date(
                    issue_date, invoice.payment_terms_days, None, client, business
                )

        # Regenerate the auto-number when the date or document type changes, but
        # NEVER overwrite a manual/custom invoice number.
        if (date_changed or doc_type_changed) and is_auto_invoice_number(invoice.invoice_number):
            invoice.invoice_number = await generate_invoice_number(
                session, invoice.issue_date, invoice.document_type
            )

        if due_date:
            invoice.due_date = due_date

        if status:
            valid_statuses = ["draft", "sent", "paid", "overdue", "cancelled"]
            if status not in valid_statuses:
                raise ValueError(f"Invalid status. Must be one of: {valid_statuses}")
            # Track when the invoice was paid for cash-basis reporting.
            if status == "paid" and invoice.status != "paid":
                invoice.paid_at = utc_now()
            elif status != "paid" and invoice.status == "paid":
                invoice.paid_at = None
            invoice.status = status

        if notes is not None:
            invoice.notes = notes

        if tax_fields_changed:
            await recalculate_invoice_totals(session, invoice)

        if client:
            await snapshot_client_info(session, client, invoice)

        invoice.updated_at = utc_now()
        await session.commit()
        await session.refresh(invoice)
        return invoice

    @staticmethod
    async def delete_invoice(session: AsyncSession, invoice_id: int) -> bool:
        """Soft delete an invoice."""
        invoice = await InvoiceService.get_invoice(session, invoice_id)
        if not invoice:
            return False

        invoice.deleted_at = utc_now()
        invoice.updated_at = utc_now()
        await session.commit()
        return True

    @staticmethod
    async def restore_invoice(session: AsyncSession, invoice_id: int) -> bool:
        """Restore a soft-deleted invoice."""
        result = await session.execute(
            select(Invoice).where(and_(Invoice.id == invoice_id, Invoice.deleted_at.is_not(None)))
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            return False

        invoice.deleted_at = None
        invoice.updated_at = utc_now()
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
        """Add a line item to an invoice."""
        quantity = _coerce_quantity(quantity)

        unit_price = Decimal(str(unit_price))
        if unit_price < 0:
            raise ValueError("Unit price cannot be negative")

        valid_unit_types = ["qty", "hours"]
        if unit_type not in valid_unit_types:
            raise ValueError(f"Invalid unit type. Must be one of: {valid_unit_types}")

        item = InvoiceItem(
            invoice_id=invoice_id,
            description=description,
            quantity=quantity,
            unit_type=unit_type,
            unit_price=unit_price,
            total=line_item_total(unit_price, quantity),
            sort_order=sort_order,
        )
        session.add(item)
        await session.flush()

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
        description: str | None = None,
        quantity: int | None = None,
        unit_price: Decimal | float | str | None = None,
        sort_order: int | None = None,
        unit_type: str | None = None,
        invoice_id: int | None = None,
    ) -> InvoiceItem | None:
        """Update a line item and keep parent invoice totals in sync."""
        item = await session.get(InvoiceItem, item_id)
        if not item:
            return None

        if invoice_id is not None and item.invoice_id != invoice_id:
            raise ValueError("Item does not belong to the specified invoice")
        if quantity is not None:
            quantity = _coerce_quantity(quantity)
        if unit_price is not None and Decimal(str(unit_price)) < 0:
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

        item.total = line_item_total(item.unit_price, item.quantity)
        await recalculate_invoice_totals(session, item.invoice)

        await session.commit()
        await session.refresh(item)
        return item

    @staticmethod
    async def remove_item(
        session: AsyncSession,
        item_id: int,
        invoice_id: int | None = None,
    ) -> bool:
        """Remove a line item and keep parent invoice totals in sync."""
        item = await session.get(InvoiceItem, item_id)
        if not item:
            return False

        if invoice_id is not None and item.invoice_id != invoice_id:
            raise ValueError("Item does not belong to the specified invoice")

        item_invoice_id = item.invoice_id
        await session.delete(item)

        invoice = await session.get(Invoice, item_invoice_id)
        if invoice:
            await recalculate_invoice_totals(session, invoice)

        await session.commit()
        return True

    @staticmethod
    async def update_overdue_invoices(session: AsyncSession) -> int:
        """Mark sent invoices as overdue when due_date has passed."""
        result = await session.execute(
            update(Invoice)
            .where(
                and_(
                    Invoice.status == "sent",
                    Invoice.due_date < utc_now().date(),
                    Invoice.deleted_at.is_(None),
                )
            )
            .values(status="overdue", updated_at=utc_now())
        )
        await session.commit()
        return result.rowcount

    @staticmethod
    async def bulk_action(
        session: AsyncSession,
        action: str,
        invoice_ids: list[int],
    ) -> dict:
        """Execute a bulk action on multiple invoices with validation."""
        valid_transitions = {
            "mark_sent": ["draft"],
            "mark_paid": ["sent", "overdue"],
            "delete": ["draft", "sent", "paid", "overdue", "cancelled"],
        }

        if action not in valid_transitions:
            return {
                "action": action,
                "total_requested": len(invoice_ids),
                "successful": 0,
                "failed": len(invoice_ids),
                "errors": [{"id": invoice_id, "reason": "Invalid action"} for invoice_id in invoice_ids],
            }

        result = await session.execute(
            select(Invoice).where(and_(Invoice.id.in_(invoice_ids), Invoice.deleted_at.is_(None)))
        )
        invoices = {invoice.id: invoice for invoice in result.scalars().all()}

        valid_ids = []
        errors = []
        for invoice_id in invoice_ids:
            if invoice_id not in invoices:
                errors.append({"id": invoice_id, "reason": "Invoice not found or deleted"})
                continue

            invoice = invoices[invoice_id]
            if invoice.status not in valid_transitions[action]:
                errors.append({
                    "id": invoice_id,
                    "reason": f"Invalid status transition: {invoice.status} cannot be {action.replace('_', ' ')}",
                })
                continue

            valid_ids.append(invoice_id)

        successful = 0
        if valid_ids:
            now = utc_now()
            if action == "mark_sent":
                await session.execute(
                    update(Invoice)
                    .where(Invoice.id.in_(valid_ids))
                    .values(status="sent", updated_at=now)
                )
            elif action == "mark_paid":
                await session.execute(
                    update(Invoice)
                    .where(Invoice.id.in_(valid_ids))
                    .values(status="paid", paid_at=now, updated_at=now)
                )
            else:
                await session.execute(
                    update(Invoice)
                    .where(Invoice.id.in_(valid_ids))
                    .values(deleted_at=now, updated_at=now)
                )
            successful = len(valid_ids)
            await session.commit()

        return {
            "action": action,
            "total_requested": len(invoice_ids),
            "successful": successful,
            "failed": len(errors),
            "errors": errors,
        }
