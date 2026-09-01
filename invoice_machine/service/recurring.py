"""Recurring schedule service operations."""

import json
import logging
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import BusinessProfile, Client, RecurringSchedule
from invoice_machine.service.common import (
    _align_to_quarter_month,
    _align_to_year_month,
    _replace_with_valid_day,
    normalize_line_items,
    validate_recurring_schedule,
)
from invoice_machine.service.reminders import business_now
from invoice_machine.utils import utc_now

logger = logging.getLogger(__name__)

# Cap invoices generated for a single schedule in one catch-up run, so a long
# outage (or a misconfigured far-past next_invoice_date) can't flood the system.
_MAX_CATCHUP_PER_SCHEDULE = 366


async def _business_today(session: AsyncSession) -> date:
    return business_now(await BusinessProfile.get(session)).date()


def _dump_payment_methods(value: list[str] | str | None) -> str | None:
    """Normalize selected payment method IDs to the stored JSON string."""
    if value is None or isinstance(value, str):
        return value or None
    return json.dumps([str(item) for item in value]) if value else None


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
        schedule_month: int | None = None,
        quarter_month: int = 1,
        use_default_notes: int = 1,
        show_payment_instructions: int = 1,
        selected_payment_methods: list[str] | str | None = None,
        auto_email_enabled: int = 0,
        email_subject_template: str | None = None,
        email_body_template: str | None = None,
    ) -> RecurringSchedule:
        """Create a new recurring schedule."""
        validate_recurring_schedule(
            frequency,
            schedule_day,
            payment_terms_days=payment_terms_days,
            tax_rate=tax_rate,
            schedule_month=schedule_month,
            quarter_month=quarter_month,
        )

        client = await session.get(Client, client_id)
        if client is None or client.deleted_at is not None:
            raise ValueError(f"Client {client_id} not found")

        if next_invoice_date is None:
            next_invoice_date = RecurringService.initial_next_date(
                await _business_today(session),
                frequency,
                schedule_day,
                schedule_month,
                quarter_month,
            )

        # Validate items now so a bad description/quantity/price is rejected at
        # save time rather than failing on every later generation run.
        if line_items is not None:
            line_items = normalize_line_items(line_items)

        schedule = RecurringSchedule(
            client_id=client_id,
            name=name,
            frequency=frequency,
            schedule_day=schedule_day,
            schedule_month=schedule_month,
            quarter_month=quarter_month,
            currency_code=currency_code,
            payment_terms_days=payment_terms_days,
            notes=notes,
            use_default_notes=use_default_notes,
            # default=str so Decimal quantities/prices serialize cleanly.
            line_items=json.dumps(line_items, default=str) if line_items else None,
            show_payment_instructions=show_payment_instructions,
            selected_payment_methods=_dump_payment_methods(selected_payment_methods),
            auto_email_enabled=auto_email_enabled,
            email_subject_template=email_subject_template,
            email_body_template=email_body_template,
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
    async def get_schedule(session: AsyncSession, schedule_id: int) -> RecurringSchedule | None:
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

    # Fields a caller may set. Anything else (id, client_id, timestamps,
    # last_invoice_id) is ignored rather than blindly setattr'd onto the model.
    _UPDATABLE_FIELDS = frozenset(  # noqa: RUF012
        {
            "name",
            "frequency",
            "schedule_day",
            "schedule_month",
            "quarter_month",
            "currency_code",
            "payment_terms_days",
            "notes",
            "use_default_notes",
            "line_items",
            "show_payment_instructions",
            "selected_payment_methods",
            "auto_email_enabled",
            "email_subject_template",
            "email_body_template",
            "tax_enabled",
            "tax_rate",
            "tax_name",
            "is_active",
            "next_invoice_date",
        }
    )

    # Fields that may legitimately be set back to NULL ("inherit the default").
    _NULLABLE_FIELDS = frozenset(  # noqa: RUF012
        {
            "notes",
            "tax_enabled",
            "tax_rate",
            "tax_name",
            "schedule_month",
            "selected_payment_methods",
            "email_subject_template",
            "email_body_template",
        }
    )

    @staticmethod
    async def update_schedule(
        session: AsyncSession, schedule_id: int, **kwargs
    ) -> RecurringSchedule | None:
        """Update a recurring schedule."""
        schedule = await RecurringService.get_schedule(session, schedule_id)
        if not schedule:
            return None

        kwargs = {k: v for k, v in kwargs.items() if k in RecurringService._UPDATABLE_FIELDS}

        if "line_items" in kwargs and kwargs["line_items"] is not None:
            kwargs["line_items"] = json.dumps(
                normalize_line_items(kwargs["line_items"]), default=str
            )
        if "selected_payment_methods" in kwargs:
            kwargs["selected_payment_methods"] = _dump_payment_methods(
                kwargs["selected_payment_methods"]
            )

        new_frequency = kwargs.get("frequency") or schedule.frequency
        new_schedule_day = kwargs.get("schedule_day")
        if new_schedule_day is None:
            new_schedule_day = schedule.schedule_day
        new_schedule_month = (
            kwargs["schedule_month"] if "schedule_month" in kwargs else schedule.schedule_month
        )
        new_quarter_month = kwargs.get("quarter_month") or schedule.quarter_month or 1
        new_payment_terms_days = kwargs.get("payment_terms_days", schedule.payment_terms_days)
        new_tax_rate = kwargs.get("tax_rate", schedule.tax_rate)

        validate_recurring_schedule(
            new_frequency,
            new_schedule_day,
            payment_terms_days=new_payment_terms_days,
            tax_rate=new_tax_rate,
            schedule_month=new_schedule_month,
            quarter_month=new_quarter_month,
        )

        # Only recompute the next run when the cadence actually CHANGES. The UI
        # submits the whole form on every save, so keying off mere presence reset
        # next_invoice_date on unrelated edits (renaming a schedule, editing line
        # items) and silently skipped or duplicated a billing period.
        cadence_changed = (
            new_frequency != schedule.frequency
            or new_schedule_day != schedule.schedule_day
            or new_schedule_month != schedule.schedule_month
            or new_quarter_month != (schedule.quarter_month or 1)
        )
        if cadence_changed and "next_invoice_date" not in kwargs:
            kwargs["next_invoice_date"] = RecurringService.initial_next_date(
                await _business_today(session),
                new_frequency,
                new_schedule_day,
                new_schedule_month,
                new_quarter_month,
            )

        for key, value in kwargs.items():
            if value is None and key not in RecurringService._NULLABLE_FIELDS:
                continue
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
    def initial_next_date(
        today: date,
        frequency: str,
        schedule_day: int,
        schedule_month: int | None = None,
        quarter_month: int = 1,
    ) -> date:
        """Compute the first invoice date for a new or rescheduled schedule.

        Uses the current period when its scheduled day hasn't passed yet, otherwise
        the next period — so a monthly schedule created on the 5th with schedule_day
        20 bills *this* month, not next. (daily/weekly already pick the soonest
        upcoming occurrence in ``calculate_next_date``.)
        """
        if frequency == "monthly":
            candidate = _replace_with_valid_day(today, schedule_day)
            if candidate >= today:
                return candidate
        elif frequency == "quarterly":
            candidate = _align_to_quarter_month(today, quarter_month, schedule_day)
            if candidate >= today:
                return candidate
        elif frequency == "yearly":
            candidate = _align_to_year_month(today, schedule_month, schedule_day)
            if candidate >= today:
                return candidate
        return RecurringService.calculate_next_date(
            today, frequency, schedule_day, schedule_month, quarter_month
        )

    @staticmethod
    def calculate_next_date(
        current_date: date,
        frequency: str,
        schedule_day: int,
        schedule_month: int | None = None,
        quarter_month: int = 1,
    ) -> date:
        """Calculate the next invoice date based on frequency.

        ``quarter_month`` (1-3) selects which month of the quarter a quarterly
        schedule bills in; ``schedule_month`` (1-12) selects the month for a
        yearly schedule. Both were configurable in the UI but previously ignored,
        so a "yearly in March" schedule billed in whatever month it was created.
        """
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
            return _align_to_quarter_month(
                current_date + relativedelta(months=3), quarter_month, schedule_day
            )
        if frequency == "yearly":
            return _align_to_year_month(
                current_date + relativedelta(years=1), schedule_month, schedule_day
            )
        raise ValueError(f"Unknown frequency: {frequency}")

    @staticmethod
    async def _create_invoice_from_schedule(
        session: AsyncSession,
        schedule: RecurringSchedule,
        issue_date: date,
    ):
        """Create one invoice from a schedule's template settings."""
        from invoice_machine.service.invoices import InvoiceService

        notes = schedule.notes
        if schedule.use_default_notes:
            profile = await BusinessProfile.get_or_create(session)
            notes = profile.default_notes

        return await InvoiceService.create_invoice(
            session,
            client_id=schedule.client_id,
            issue_date=issue_date,
            currency_code=schedule.currency_code,
            payment_terms_days=schedule.payment_terms_days,
            notes=notes,
            items=schedule.line_items_list,
            tax_enabled=schedule.tax_enabled,
            tax_rate=schedule.tax_rate,
            tax_name=schedule.tax_name,
            show_payment_instructions=bool(schedule.show_payment_instructions),
            selected_payment_methods=schedule.selected_payment_methods,
            commit=False,
        )

    @staticmethod
    async def _auto_email_invoice(
        session: AsyncSession, schedule: RecurringSchedule, invoice_id: int
    ) -> dict | None:
        """Email a freshly generated invoice when the schedule opts in.

        A delivery failure is logged and reported but never aborts generation —
        the invoice itself is already committed.
        """
        if not schedule.auto_email_enabled:
            return None

        from invoice_machine.service.email import send_invoice_email

        try:
            return await send_invoice_email(
                session,
                invoice_id,
                subject=schedule.email_subject_template or None,
                body=schedule.email_body_template or None,
            )
        except Exception as exc:
            logger.error(
                "Auto-email for recurring schedule %s failed: %s", schedule.id, exc, exc_info=True
            )
            return {"success": False, "error": str(exc)}

    @staticmethod
    async def process_due_schedules(session: AsyncSession) -> list[dict]:
        """Process all schedules due today or earlier and create invoices.

        For each due schedule this generates one invoice per *missed period*
        (catch-up), dating each invoice on its own period date and advancing the
        schedule from the period date (not "today") so the cadence never drifts.
        next_invoice_date is advanced and committed after each invoice, so a
        crash mid-run cannot regenerate already-billed periods.
        """
        today = await _business_today(session)
        result = await session.execute(
            select(RecurringSchedule)
            .join(Client, RecurringSchedule.client_id == Client.id)
            .where(
                RecurringSchedule.is_active == 1,
                RecurringSchedule.next_invoice_date <= today,
                Client.deleted_at.is_(None),
            )
        )
        due_ids = [schedule.id for schedule in result.scalars().all()]

        results = []
        # Re-fetch by id each iteration: a rollback in the except expires every
        # loaded instance, and reading an expired attribute would raise
        # MissingGreenlet (a lazy reload) and abort the rest of the run.
        for schedule_id in due_ids:
            schedule = await session.get(RecurringSchedule, schedule_id)
            if schedule is None:
                continue
            schedule_name = schedule.name
            generated = 0
            try:
                while schedule.next_invoice_date <= today and generated < _MAX_CATCHUP_PER_SCHEDULE:
                    period_date = schedule.next_invoice_date
                    invoice = await RecurringService._create_invoice_from_schedule(
                        session, schedule, period_date
                    )
                    # create_invoice may roll back on a numbering retry, which
                    # expires this instance; re-fetch before reading its fields.
                    schedule = await session.get(RecurringSchedule, schedule_id)

                    schedule.last_invoice_id = invoice.id
                    schedule.next_invoice_date = RecurringService.calculate_next_date(
                        period_date,
                        schedule.frequency,
                        schedule.schedule_day,
                        schedule.schedule_month,
                        schedule.quarter_month,
                    )
                    schedule.updated_at = utc_now()
                    # Invoice and schedule advance commit together so a crash
                    # cannot regenerate this period.
                    await session.commit()
                    generated += 1

                    entry = {
                        "schedule_id": schedule_id,
                        "schedule_name": schedule_name,
                        "invoice_id": invoice.id,
                        "invoice_number": invoice.invoice_number,
                        "issue_date": period_date.isoformat(),
                        "success": True,
                    }
                    email_result = await RecurringService._auto_email_invoice(
                        session, schedule, invoice.id
                    )
                    if email_result is not None:
                        entry["emailed"] = bool(email_result.get("success"))
                        if not email_result.get("success"):
                            entry["email_error"] = email_result.get("error")
                    results.append(entry)

                if generated >= _MAX_CATCHUP_PER_SCHEDULE and schedule.next_invoice_date <= today:
                    logger.warning(
                        "Recurring schedule %s (%s) hit the %s-invoice catch-up cap; "
                        "remaining periods will generate on the next run.",
                        schedule_id,
                        schedule_name,
                        _MAX_CATCHUP_PER_SCHEDULE,
                    )
            except Exception as exc:
                await session.rollback()
                logger.error(
                    "Recurring schedule %s failed after generating %s invoice(s): %s",
                    schedule_id,
                    generated,
                    exc,
                    exc_info=True,
                )
                results.append(
                    {
                        "schedule_id": schedule_id,
                        "schedule_name": schedule_name,
                        "invoices_generated": generated,
                        "success": False,
                        "error": str(exc),
                    }
                )

        return results

    @staticmethod
    async def trigger_schedule(session: AsyncSession, schedule_id: int) -> dict:
        """Manually trigger a schedule to create an invoice now."""
        schedule = await RecurringService.get_schedule(session, schedule_id)
        if not schedule:
            return {"success": False, "error": "Schedule not found"}

        today = await _business_today(session)
        try:
            invoice = await RecurringService._create_invoice_from_schedule(session, schedule, today)

            schedule.last_invoice_id = invoice.id
            # Advance only if this manual run covers the pending period; otherwise
            # an ad-hoc invoice would silently cancel the next scheduled billing.
            if schedule.next_invoice_date <= today:
                schedule.next_invoice_date = RecurringService.calculate_next_date(
                    schedule.next_invoice_date,
                    schedule.frequency,
                    schedule.schedule_day,
                    schedule.schedule_month,
                    schedule.quarter_month,
                )
            schedule.updated_at = utc_now()
            await session.commit()

            result = {
                "success": True,
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "next_invoice_date": schedule.next_invoice_date.isoformat(),
            }
            email_result = await RecurringService._auto_email_invoice(session, schedule, invoice.id)
            if email_result is not None:
                result["emailed"] = bool(email_result.get("success"))
                if not email_result.get("success"):
                    result["email_error"] = email_result.get("error")
            return result
        except Exception as exc:
            # Leave the session usable for the caller / next request.
            await session.rollback()
            logger.error(
                "Manual trigger of schedule %s failed: %s", schedule_id, exc, exc_info=True
            )
            return {"success": False, "error": str(exc)}
