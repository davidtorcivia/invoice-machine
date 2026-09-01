"""Shared tool annotations for the MCP server.

The four hints (MCP `ToolAnnotations`) are advisory - a client may ignore them,
so they are a UX signal, never access control. Real enforcement stays in the
service layer.
"""

from __future__ import annotations

from mcp_types import ToolAnnotations

# Pure lookups: safe to call freely, safe to retry.
READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

# Reads that reach an external service (so they can fail or hang on the
# network) but still change nothing.
READ_ONLY_REMOTE = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

# Creates a new record. Not idempotent: calling twice creates two of them.
ADDITIVE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)

# Creates or refreshes a derived artifact where a repeat call just redoes the
# same work (regenerating a PDF, restoring an already-restored record).
ADDITIVE_IDEMPOTENT = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

# Edits fields on an existing record. Not destructive - it overwrites the
# fields you name and leaves the row in place - and settling on the same values
# twice is a no-op.
UPDATE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

# Removes a record or reverses a financial entry. Most deletes here are soft,
# but the record still leaves every normal view.
DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)

# Sends something a customer can see, or moves money through a provider. Not
# idempotent and not undoable; these tools also ask for confirmation.
OUTWARD = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)

# Reverses money through a provider. Destructive *and* outward, but carries an
# idempotency key, so a retry is safe.
OUTWARD_REVERSAL = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
    open_world_hint=True,
)
