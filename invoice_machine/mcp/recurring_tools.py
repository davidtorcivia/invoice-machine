"""Recurring schedule MCP tools."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from invoice_machine.presenters import serialize_recurring_schedule
from invoice_machine.services import RecurringService

from .context import get_session, mcp


@mcp.tool()
async def list_recurring_schedules(
    client_id: int | None = None,
    include_paused: bool = False,
) -> list:
    """
    List recurring invoice schedules.

    Args:
        client_id: Filter by client ID
        include_paused: Include paused schedules (default: False, only active)

    Returns:
        List of recurring schedules with their details
    """
    async with get_session() as session:
        schedules = await RecurringService.list_schedules(
            session,
            client_id=client_id,
            active_only=not include_paused,
        )
        return [serialize_recurring_schedule(schedule, json_ready=True) for schedule in schedules]


@mcp.tool()
async def get_recurring_schedule(schedule_id: int) -> dict | None:
    """
    Get a recurring schedule by ID.

    Args:
        schedule_id: The schedule ID

    Returns:
        Schedule details or null if not found
    """
    async with get_session() as session:
        schedule = await RecurringService.get_schedule(session, schedule_id)
        if not schedule:
            return None
        return serialize_recurring_schedule(schedule, json_ready=True)


@mcp.tool()
async def create_recurring_schedule(
    client_id: int,
    name: str,
    frequency: str,
    items: list,
    schedule_day: int = 1,
    currency_code: str = "USD",
    payment_terms_days: int = 30,
    notes: str | None = None,
    next_invoice_date: str | None = None,
    tax_enabled: int | None = None,
    tax_rate: float | None = None,
    tax_name: str | None = None,
) -> dict:
    """
    Create a recurring invoice schedule.

    Args:
        client_id: Client ID for the recurring invoices
        name: Schedule name (e.g., "Monthly Retainer", "Quarterly Hosting")
        frequency: One of: daily, weekly, monthly, quarterly, yearly
        items: Line items: [{description, quantity, unit_price, unit_type}]
        schedule_day: Day of month (1-31) for monthly/quarterly/yearly,
                      or day of week (0=Mon, 6=Sun) for weekly
        currency_code: Currency code (default: USD)
        payment_terms_days: Payment terms in days (default: 30)
        notes: Invoice notes
        next_invoice_date: First invoice date (ISO format, defaults to next scheduled date)
        tax_enabled: Override tax setting (None = use client/global default)
        tax_rate: Override tax rate
        tax_name: Override tax name

    Returns:
        Created schedule details
    """

    async with get_session() as session:
        # Parse next_invoice_date if provided
        parsed_date = None
        if next_invoice_date:
            parsed_date = date.fromisoformat(next_invoice_date)

        # Convert tax_rate to Decimal if provided
        tax_rate_decimal = Decimal(str(tax_rate)) if tax_rate is not None else None

        schedule = await RecurringService.create_schedule(
            session,
            client_id=client_id,
            name=name,
            frequency=frequency,
            schedule_day=schedule_day,
            currency_code=currency_code,
            payment_terms_days=payment_terms_days,
            notes=notes,
            line_items=items,
            next_invoice_date=parsed_date,
            tax_enabled=tax_enabled,
            tax_rate=tax_rate_decimal,
            tax_name=tax_name,
        )

        return serialize_recurring_schedule(schedule, json_ready=True)


@mcp.tool()
async def update_recurring_schedule(
    schedule_id: int,
    name: str | None = None,
    frequency: str | None = None,
    schedule_day: int | None = None,
    currency_code: str | None = None,
    payment_terms_days: int | None = None,
    notes: str | None = None,
    items: list | None = None,
    next_invoice_date: str | None = None,
    tax_enabled: int | None = None,
    tax_rate: float | None = None,
    tax_name: str | None = None,
) -> dict | None:
    """
    Update a recurring schedule.

    Only provide the fields you want to change.

    Args:
        schedule_id: The schedule ID
        name: Schedule name
        frequency: One of: daily, weekly, monthly, quarterly, yearly
        schedule_day: Day of month/week
        currency_code: Currency code
        payment_terms_days: Payment terms in days
        notes: Invoice notes
        items: Line items: [{description, quantity, unit_price, unit_type}]
        next_invoice_date: Next invoice date (ISO format)
        tax_enabled: Tax setting override
        tax_rate: Tax rate override
        tax_name: Tax name override

    Returns:
        Updated schedule or null if not found
    """

    async with get_session() as session:
        updates = {}
        if name is not None:
            updates["name"] = name
        if frequency is not None:
            updates["frequency"] = frequency
        if schedule_day is not None:
            updates["schedule_day"] = schedule_day
        if currency_code is not None:
            updates["currency_code"] = currency_code
        if payment_terms_days is not None:
            updates["payment_terms_days"] = payment_terms_days
        if notes is not None:
            updates["notes"] = notes
        if items is not None:
            updates["line_items"] = items
        if next_invoice_date is not None:
            updates["next_invoice_date"] = date.fromisoformat(next_invoice_date)
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


@mcp.tool()
async def delete_recurring_schedule(schedule_id: int) -> bool:
    """
    Delete a recurring schedule.

    Args:
        schedule_id: The schedule ID

    Returns:
        True if deleted, False if not found
    """
    async with get_session() as session:
        return await RecurringService.delete_schedule(session, schedule_id)


@mcp.tool()
async def pause_recurring_schedule(schedule_id: int) -> bool:
    """
    Pause a recurring schedule.

    Paused schedules won't generate invoices until resumed.

    Args:
        schedule_id: The schedule ID

    Returns:
        True if paused, False if not found
    """
    async with get_session() as session:
        return await RecurringService.pause_schedule(session, schedule_id)


@mcp.tool()
async def resume_recurring_schedule(schedule_id: int) -> bool:
    """
    Resume a paused recurring schedule.

    Args:
        schedule_id: The schedule ID

    Returns:
        True if resumed, False if not found
    """
    async with get_session() as session:
        return await RecurringService.resume_schedule(session, schedule_id)


@mcp.tool()
async def trigger_recurring_schedule(schedule_id: int) -> dict:
    """
    Manually trigger a recurring schedule to create an invoice now.

    This creates an invoice immediately and updates the next scheduled date.

    Args:
        schedule_id: The schedule ID

    Returns:
        Result with invoice details or error
    """
    async with get_session() as session:
        return await RecurringService.trigger_schedule(session, schedule_id)


# Import for type references


