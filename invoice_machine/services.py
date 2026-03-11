"""Compatibility exports for the service layer."""

from datetime import date  # noqa: F401 — accessed via compat.date by service modules

import boto3  # noqa: F401 — accessed via compat.boto3 by BackupService

from invoice_machine.config import get_settings  # noqa: F401 — accessed via compat.get_settings
from invoice_machine.service.backups import BackupService, get_backup_service
from invoice_machine.service.clients import ClientService
from invoice_machine.service.common import (
    VALID_RECURRING_FREQUENCIES,
    _replace_with_valid_day,
    calculate_due_date,
    format_currency,
    generate_invoice_number,
    is_invoice_document,
    purge_trashed_records,
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
    "purge_trashed_records",
    "recalculate_invoice_totals",
    "snapshot_client_info",
    "validate_recurring_schedule",
]
