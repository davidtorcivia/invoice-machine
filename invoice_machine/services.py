"""Compatibility exports for the service layer."""

from invoice_machine.service.backups import BackupService, get_backup_service
from invoice_machine.service.clients import ClientService
from invoice_machine.service.common import (
    VALID_RECURRING_FREQUENCIES,
    _replace_with_valid_day,
    calculate_due_date,
    format_currency,
    generate_invoice_number,
    is_invoice_document,
    line_item_total,
    purge_trashed_records,
    quantize_money,
    recalculate_invoice_totals,
    snapshot_client_info,
    validate_recurring_schedule,
)
from invoice_machine.service.invoices import InvoiceService
from invoice_machine.service.recurring import RecurringService
from invoice_machine.service.search import SearchService

__all__ = [
    "BackupService",
    "ClientService",
    "InvoiceService",
    "RecurringService",
    "SearchService",
    "VALID_RECURRING_FREQUENCIES",
    "_replace_with_valid_day",
    "calculate_due_date",
    "format_currency",
    "generate_invoice_number",
    "get_backup_service",
    "is_invoice_document",
    "line_item_total",
    "purge_trashed_records",
    "quantize_money",
    "recalculate_invoice_totals",
    "snapshot_client_info",
    "validate_recurring_schedule",
]
