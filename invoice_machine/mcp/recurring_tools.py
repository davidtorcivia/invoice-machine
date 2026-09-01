"""Recurring schedule MCP tools."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from mcp.server.mcpserver import Context, Elicit, Resolve

from invoice_machine.presenters import serialize_recurring_schedule
from invoice_machine.services import RecurringService

from .annotations import ADDITIVE, DESTRUCTIVE, OUTWARD, READ_ONLY, UPDATE
from .confirmations import Confirmation, confirmed, ensure_confirmed
from .context import get_session, mcp
from .schemas import RecurringScheduleOut


@mcp.tool(annotations=READ_ONLY)
async def list_recurring_schedules(
    client_id: int | None = None,
    include_paused: bool = False,
) -> list[RecurringScheduleOut]:
    """List recurring invoice schedules (active only unless include_paused)."""
    async with get_session() as session:
        schedules = await RecurringService.list_schedules(
            session,
            client_id=client_id,
            active_only=not include_paused,
        )
        return [serialize_recurring_schedule(schedule, json_ready=True) for schedule in schedules]


@mcp.tool(annotations=READ_ONLY)
async def get_recurring_schedule(schedule_id: int) -> RecurringScheduleOut | None:
    """Get a recurring schedule by ID."""
    async with get_session() as session:
        schedule = await RecurringService.get_schedule(session, schedule_id)
        if not schedule:
            return None
        return serialize_recurring_schedule(schedule, json_ready=True)


@mcp.tool(annotations=ADDITIVE)
async def create_recurring_schedule(
    client_id: int,
    name: str,
    frequency: str,
    items: list,
    schedule_day: int = 1,
    schedule_month: int | None = None,
    quarter_month: int = 1,
    currency_code: str = "USD",
    payment_terms_days: int = 30,
    notes: str | None = None,
    use_default_notes: bool = False,
    next_invoice_date: str | None = None,
    show_payment_instructions: bool = True,
    selected_payment_methods: list[str] | None = None,
    auto_email_enabled: bool = False,
    email_subject_template: str | None = None,
    email_body_template: str | None = None,
    tax_enabled: int | None = None,
    tax_rate: float | None = None,
    tax_name: str | None = None,
) -> RecurringScheduleOut:
    """
    Create a recurring invoice schedule.

    Args:
        name: Schedule name (e.g., "Monthly Retainer", "Quarterly Hosting")
        frequency: One of: daily, weekly, monthly, quarterly, yearly
        items: Line items: [{description, quantity, unit_price, unit_type}]
        schedule_day: Day of month (1-31) for monthly/quarterly/yearly,
                      or day of week (0=Mon, 6=Sun) for weekly
        schedule_month: Calendar month (1-12) for yearly schedules
        quarter_month: Which month within each quarter (1-3) for quarterly schedules
        use_default_notes: Use the business profile's default notes instead of `notes`
        next_invoice_date: First invoice date (ISO format, defaults to next scheduled date)
        selected_payment_methods: Payment method IDs to show on generated invoices
        auto_email_enabled: Email each generated invoice to the client automatically
        tax_enabled: Override tax setting (None = use client/global default)
    """

    async with get_session() as session:
        parsed_date = None
        if next_invoice_date:
            parsed_date = date.fromisoformat(next_invoice_date)

        tax_rate_decimal = Decimal(str(tax_rate)) if tax_rate is not None else None

        schedule = await RecurringService.create_schedule(
            session,
            client_id=client_id,
            name=name,
            frequency=frequency,
            schedule_day=schedule_day,
            schedule_month=schedule_month,
            quarter_month=quarter_month,
            currency_code=currency_code,
            payment_terms_days=payment_terms_days,
            notes=notes,
            use_default_notes=int(use_default_notes),
            line_items=items,
            show_payment_instructions=int(show_payment_instructions),
            selected_payment_methods=selected_payment_methods,
            auto_email_enabled=int(auto_email_enabled),
            email_subject_template=email_subject_template,
            email_body_template=email_body_template,
            next_invoice_date=parsed_date,
            tax_enabled=tax_enabled,
            tax_rate=tax_rate_decimal,
            tax_name=tax_name,
        )

        return serialize_recurring_schedule(schedule, json_ready=True)


@mcp.tool(annotations=UPDATE)
async def update_recurring_schedule(
    schedule_id: int,
    name: str | None = None,
    frequency: str | None = None,
    schedule_day: int | None = None,
    schedule_month: int | None = None,
    quarter_month: int | None = None,
    currency_code: str | None = None,
    payment_terms_days: int | None = None,
    notes: str | None = None,
    use_default_notes: bool | None = None,
    items: list | None = None,
    next_invoice_date: str | None = None,
    show_payment_instructions: bool | None = None,
    selected_payment_methods: list[str] | None = None,
    auto_email_enabled: bool | None = None,
    email_subject_template: str | None = None,
    email_body_template: str | None = None,
    tax_enabled: int | None = None,
    tax_rate: float | None = None,
    tax_name: str | None = None,
) -> RecurringScheduleOut | None:
    """
    Update a recurring schedule. Only provide the fields you want to change.

    Args:
        frequency: One of: daily, weekly, monthly, quarterly, yearly
        schedule_day: Day of month (1-31), or day of week (0=Mon, 6=Sun) for weekly
        schedule_month: Calendar month (1-12) for yearly schedules
        quarter_month: Which month within each quarter (1-3) for quarterly schedules
        use_default_notes: Use the business profile's default notes instead of `notes`
        items: Line items: [{description, quantity, unit_price, unit_type}]
        next_invoice_date: Next invoice date (ISO format)
        selected_payment_methods: Payment method IDs to show on generated invoices
        auto_email_enabled: Email each generated invoice to the client automatically
    """

    async with get_session() as session:
        updates = {}
        if name is not None:
            updates["name"] = name
        if frequency is not None:
            updates["frequency"] = frequency
        if schedule_day is not None:
            updates["schedule_day"] = schedule_day
        if schedule_month is not None:
            updates["schedule_month"] = schedule_month
        if quarter_month is not None:
            updates["quarter_month"] = quarter_month
        if currency_code is not None:
            updates["currency_code"] = currency_code
        if payment_terms_days is not None:
            updates["payment_terms_days"] = payment_terms_days
        if notes is not None:
            updates["notes"] = notes
        if use_default_notes is not None:
            updates["use_default_notes"] = int(use_default_notes)
        if items is not None:
            updates["line_items"] = items
        if next_invoice_date is not None:
            updates["next_invoice_date"] = date.fromisoformat(next_invoice_date)
        if show_payment_instructions is not None:
            updates["show_payment_instructions"] = int(show_payment_instructions)
        if selected_payment_methods is not None:
            updates["selected_payment_methods"] = selected_payment_methods
        if auto_email_enabled is not None:
            updates["auto_email_enabled"] = int(auto_email_enabled)
        if email_subject_template is not None:
            updates["email_subject_template"] = email_subject_template
        if email_body_template is not None:
            updates["email_body_template"] = email_body_template
        if tax_enabled is not None:
            updates["tax_enabled"] = tax_enabled
        if tax_rate is not None:
            updates["tax_rate"] = Decimal(str(tax_rate))
        if tax_name is not None:
            updates["tax_name"] = tax_name

        schedule = await RecurringService.update_schedule(session, schedule_id, **updates)
        if not schedule:
            return None

        return serialize_recurring_schedule(schedule, json_ready=True)


@mcp.tool(annotations=DESTRUCTIVE)
async def delete_recurring_schedule(schedule_id: int) -> bool:
    """Delete a recurring schedule."""
    async with get_session() as session:
        return await RecurringService.delete_schedule(session, schedule_id)


@mcp.tool(annotations=UPDATE)
async def pause_recurring_schedule(schedule_id: int) -> bool:
    """Pause a recurring schedule; it generates no invoices until resumed."""
    async with get_session() as session:
        return await RecurringService.pause_schedule(session, schedule_id)


@mcp.tool(annotations=UPDATE)
async def resume_recurring_schedule(schedule_id: int) -> bool:
    """Resume a paused recurring schedule."""
    async with get_session() as session:
        return await RecurringService.resume_schedule(session, schedule_id)


async def _confirm_trigger(
    schedule_id: int,
    ctx: Context,
) -> Confirmation | Elicit[Confirmation]:
    """Ask before an off-cycle run, since it also moves the next due date."""
    async with get_session() as session:
        schedule = await RecurringService.get_schedule(session, schedule_id)
        label = getattr(schedule, "name", None) or f"schedule {schedule_id}"

    return confirmed(
        ctx,
        f"Trigger {label} now? This creates an invoice immediately and advances "
        "the next scheduled date.",
    )


@mcp.tool(annotations=OUTWARD)
async def trigger_recurring_schedule(
    schedule_id: int,
    confirmation: Annotated[Confirmation, Resolve(_confirm_trigger)],
) -> dict:
    """
    Manually trigger a recurring schedule to create an invoice now.

    This creates an invoice immediately and updates the next scheduled date.
    Asks the user to confirm first, where the client supports it.
    """
    ensure_confirmed(confirmation, "Triggering this schedule")

    async with get_session() as session:
        return await RecurringService.trigger_schedule(session, schedule_id)
