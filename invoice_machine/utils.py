"""Utility helpers for validation and safe filenames."""

from __future__ import annotations

import ipaddress
import re
import socket
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

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


def refuse_disallowed_host(
    host: str, port: int = 443, *, kind: str = "host", require_resolve: bool = True
) -> None:
    """Refuse a hostname that resolves to loopback, link-local, or metadata.

    Private LAN ranges (RFC1918) are allowed so a self-hoster can reach mail
    or MinIO on their own network. DNS resolution is blocking; call this off
    the event loop. ``require_resolve=False`` skips hosts that do not resolve
    so the caller (boto3) can report its own error.
    """
    if not host:
        raise ValueError(f"{kind} is not configured.")
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        if require_resolve:
            raise ValueError(f"{kind} '{host}' could not be resolved") from exc
        return

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(
                f"{kind} resolves to a disallowed address "
                "(loopback/link-local/metadata). Use a routable host."
            )


def refuse_disallowed_url(url: str, *, kind: str = "URL") -> None:
    """Refuse an http(s) URL whose host would fail refuse_disallowed_host."""
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"{kind} must be http or https")
    if not parsed.hostname:
        raise ValueError(f"{kind} is missing a host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    refuse_disallowed_host(parsed.hostname, port, kind=kind, require_resolve=False)


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
