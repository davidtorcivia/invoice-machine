"""Utility helpers for validation and safe filenames."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

INVOICE_NUMBER_REGEX = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,49}$"
INVOICE_NUMBER_PATTERN = re.compile(INVOICE_NUMBER_REGEX)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetimes to timezone-aware UTC, handling legacy naive values."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def normalize_invoice_number_override(value: str) -> str:
    """Validate and normalize an invoice number override."""
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("Invoice number cannot be empty")
    if "/" in trimmed or "\\" in trimmed:
        raise ValueError("Invoice number cannot contain path separators")
    if ".." in trimmed:
        raise ValueError("Invoice number cannot contain consecutive dots")
    if not INVOICE_NUMBER_PATTERN.fullmatch(trimmed):
        raise ValueError(
            "Invoice number must be 1-50 characters and use only letters, numbers, dots, dashes, or underscores"
        )
    return trimmed


def sanitize_filename_component(value: str, fallback: str) -> str:
    """Return a filesystem-safe filename component."""
    if not value:
        return fallback
    safe = "".join(c for c in value if c.isalnum() or c in "-_")
    safe = safe.strip("-_")
    return safe or fallback


def confined_file(directory: Path, name: str) -> Path | None:
    """Resolve ``name`` inside ``directory``, or None if it would escape.

    ``name`` is treated as a single path component. Separators and ``..`` are
    rejected before resolution so a stored or user-supplied value cannot walk
    out of the intended directory, including via a prefix match
    (``/data/logos`` vs ``/data/logos-evil``).
    """
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        return None
    try:
        directory_resolved = directory.resolve()
        candidate = (directory / name).resolve()
        candidate.relative_to(directory_resolved)
    except (OSError, ValueError):
        return None
    return candidate
