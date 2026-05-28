"""Recurring schedule service operations."""

import json
import logging
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import RecurringSchedule
from invoice_machine.service.common import (
    _replace_with_valid_day,
    validate_recurring_schedule,
)
from invoice_machine.utils import utc_now

logger = logging.getLogger(__name__)

# Cap invoices generated for a single schedule in one catch-up run, so a long
# outage (or a misconfigured far-past next_invoice_date) can't flood the system.
_MAX_CATCHUP_PER_SCHEDULE = 366


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
        notes: str | None = None,
        line_items: list | None = None,
        tax_enabled: int | None = None,
        tax_rate: Decimal | None = None,
        tax_name: str | None = None,
        next_invoice_date: date | None = None,
    ) -> RecurringSchedule:
        """Create a new recurring schedule."""
        validate_recurring_schedule(
            frequency,
            schedule_day,
            payment_terms_days=payment_terms_days,
            tax_rate=tax_rate,
        )

        if next_invoice_date is None:
            today = utc_now().date()
            if frequency == "daily":
                next_invoice_date = today + timedelta(days=1)
            elif frequency == "weekly":
                days_ahead = schedule_day - today.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                next_invoice_date = today + timedelta(days=days_ahead)
            elif frequency == "monthly":
                next_invoice_date = _replace_with_valid_day(
                    today.replace(day=1) + relativedelta(months=1),
                    schedule_day,
                )
            elif frequency == "quarterly":
                next_invoice_date = _replace_with_valid_day(
                    today.replace(day=1) + relativedelta(months=3),
                    schedule_day,
                )
            else:
                next_invoice_date = _replace_with_valid_day(
                    today.replace(day=1) + relativedelta(years=1),
                    schedule_day,
                )

        schedule = RecurringSchedule(
            client_id=client_id,
            name=name,
            frequency=frequency,
            schedule_day=schedule_day,
            currency_code=currency_code,
            payment_terms_days=payment_terms_days,
            notes=notes,
            # default=str so Decimal quantities/prices serialize cleanly.
            line_items=json.dumps(line_items, default=str) if line_items else None,
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
    ) -> RecurringSchedule | None:
        """Get a recurring schedule by ID."""
        result = await session.execute(
            select(RecurringSchedule).where(RecurringSchedule.id == schedule_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_schedules(
        session: AsyncSession,
        client_id: int | None = None,
        active_only: bool = True,
    ) -> list[RecurringSchedule]:
        """List recurring schedules."""
        query = select(RecurringSchedule)
        if client_id:
            query = query.where(RecurringSchedule.client_id == client_id)
        if active_only:
            query = query.where(RecurringSchedule.is_active == 1)

        result = await session.execute(query.order_by(RecurringSchedule.next_invoice_date))
        return list(result.scalars().all())

    @staticmethod
    async def update_schedule(
        session: AsyncSession, schedule_id: int, **kwargs
    ) -> RecurringSchedule | None:
        """Update a recurring schedule."""
        schedule = await RecurringService.get_schedule(session, schedule_id)
        if not schedule:
            return None

        if "line_items" in kwargs and kwargs["line_items"] is not None:
            kwargs["line_items"] = json.dumps(kwargs["line_items"], default=str)

        new_frequency = kwargs.get("frequency", schedule.frequency)
        new_schedule_day = kwargs.get("schedule_day", schedule.schedule_day)
        new_payment_terms_days = kwargs.get("payment_terms_days", schedule.payment_terms_days)
        new_tax_rate = kwargs.get("tax_rate", schedule.tax_rate)

        validate_recurring_schedule(
            new_frequency,
            new_schedule_day,
            payment_terms_days=new_payment_terms_days,
            tax_rate=new_tax_rate,
        )

        if (
            ("frequency" in kwargs or "schedule_day" in kwargs)
            and "next_invoice_date" not in kwargs
        ):
            kwargs["next_invoice_date"] = RecurringService.calculate_next_date(
                utc_now().date(), new_frequency, new_schedule_day
            )

        for key, value in kwargs.items():
            if hasattr(schedule, key) and value is not None:
                setattr(schedule, key, value)

        schedule.updated_at = utc_now()
        await session.commit()
        await session.refresh(schedule)
        return schedule

    @staticmethod
    async def delete_schedule(session: AsyncSession, schedule_id: int) -> bool:
        """Delete a recurring schedule."""
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
        schedule.updated_at = utc_now()
        await session.commit()
        return True

    @staticmethod
    async def resume_schedule(session: AsyncSession, schedule_id: int) -> bool:
        """Resume a paused recurring schedule."""
        schedule = await RecurringService.get_schedule(session, schedule_id)
        if not schedule:
            return False

        schedule.is_active = 1
        schedule.updated_at = utc_now()
        await session.commit()
        return True

    @staticmethod
    def calculate_next_date(current_date: date, frequency: str, schedule_day: int) -> date:
        """Calculate the next invoice date based on frequency."""
        if frequency == "daily":
            return current_date + timedelta(days=1)
        if frequency == "weekly":
            days_ahead = schedule_day - current_date.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return current_date + timedelta(days=days_ahead)
        if frequency == "monthly":
            return _replace_with_valid_day(current_date + relativedelta(months=1), schedule_day)
        if frequency == "quarterly":
            return _replace_with_valid_day(current_date + relativedelta(months=3), schedule_day)
        if frequency == "yearly":
            return _replace_with_valid_day(current_date + relativedelta(years=1), schedule_day)
        raise ValueError(f"Unknown frequency: {frequency}")

    @staticmethod
    async def process_due_schedules(session: AsyncSession) -> list[dict]:
        """Process all schedules due today or earlier and create invoices.

        For each due schedule this generates one invoice per *missed period*
        (catch-up), dating each invoice on its own period date and advancing the
        schedule from the period date (not "today") so the cadence never drifts.
        next_invoice_date is advanced and committed after each invoice, so a
        crash mid-run cannot regenerate already-billed periods.
        """
        from invoice_machine.service.invoices import InvoiceService

        today = utc_now().date()
        result = await session.execute(
            select(RecurringSchedule).where(
                RecurringSchedule.is_active == 1,
                RecurringSchedule.next_invoice_date <= today,
            )
        )
        due_schedules = list(result.scalars().all())

        results = []
        for schedule in due_schedules:
            line_items = json.loads(schedule.line_items) if schedule.line_items else []
            generated = 0
            try:
                while schedule.next_invoice_date <= today and generated < _MAX_CATCHUP_PER_SCHEDULE:
                    period_date = schedule.next_invoice_date
                    invoice = await InvoiceService.create_invoice(
                        session,
                        client_id=schedule.client_id,
                        issue_date=period_date,
                        currency_code=schedule.currency_code,
                        payment_terms_days=schedule.payment_terms_days,
                        notes=schedule.notes,
                        items=line_items,
                        tax_enabled=schedule.tax_enabled,
                        tax_rate=schedule.tax_rate,
                        tax_name=schedule.tax_name,
                    )

                    schedule.last_invoice_id = invoice.id
                    schedule.next_invoice_date = RecurringService.calculate_next_date(
                        period_date, schedule.frequency, schedule.schedule_day
                    )
                    schedule.updated_at = utc_now()
                    # Persist the advance alongside the (already-committed) invoice
                    # so this period is never regenerated on a later run.
                    await session.commit()
                    generated += 1

                    results.append({
                        "schedule_id": schedule.id,
                        "schedule_name": schedule.name,
                        "invoice_id": invoice.id,
                        "invoice_number": invoice.invoice_number,
                        "issue_date": period_date.isoformat(),
                        "success": True,
                    })

                if generated >= _MAX_CATCHUP_PER_SCHEDULE and schedule.next_invoice_date <= today:
                    logger.warning(
                        "Recurring schedule %s (%s) hit the %s-invoice catch-up cap; "
                        "remaining periods will generate on the next run.",
                        schedule.id,
                        schedule.name,
                        _MAX_CATCHUP_PER_SCHEDULE,
                    )
            except Exception as exc:
                await session.rollback()
                logger.error(
                    "Recurring schedule %s failed after generating %s invoice(s): %s",
                    schedule.id,
                    generated,
                    exc,
                    exc_info=True,
                )
                results.append({
                    "schedule_id": schedule.id,
                    "schedule_name": schedule.name,
                    "invoices_generated": generated,
                    "success": False,
                    "error": str(exc),
                })

        return results

    @staticmethod
    async def trigger_schedule(session: AsyncSession, schedule_id: int) -> dict:
        """Manually trigger a schedule to create an invoice now."""
        from invoice_machine.service.invoices import InvoiceService

        schedule = await RecurringService.get_schedule(session, schedule_id)
        if not schedule:
            return {"success": False, "error": "Schedule not found"}

        today = utc_now().date()
        try:
            line_items = json.loads(schedule.line_items) if schedule.line_items else []
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

            schedule.last_invoice_id = invoice.id
            schedule.next_invoice_date = RecurringService.calculate_next_date(
                today, schedule.frequency, schedule.schedule_day
            )
            schedule.updated_at = utc_now()
            await session.commit()

            return {
                "success": True,
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "next_invoice_date": schedule.next_invoice_date.isoformat(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}
