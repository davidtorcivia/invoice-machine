"""Shared tool annotations for the MCP server.

Annotations tell a client what a tool does *before* it calls it, so it can
auto-approve a lookup and pause on something that moves money or leaves the
building. Without them every tool looks equally risky and clients have to treat
`list_invoices` like `delete_invoice`.

The four hints (MCP `ToolAnnotations`) are advisory - a client may ignore them,
so they are a UX signal, never an access control. Real enforcement stays in the
service layer.

- `read_only_hint`  - the tool does not change any state.
- `destructive_hint` - the tool may remove or reverse existing data, as opposed
  to only adding to it. Only meaningful when `read_only_hint` is false.
- `idempotent_hint` - calling it twice with the same arguments has no extra
  effect. This is the hint that stops a retrying agent from double-billing.
- `open_world_hint` - the tool touches something outside this app: an SMTP
  server, a payment provider, a client's inbox.

Prefer one of the constants below over hand-writing `ToolAnnotations`, so tools
with the same risk profile stay described the same way.
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

# Creates something, but a repeat call is a no-op rather than a second one:
# either because it just redoes the same work (regenerating a PDF, restoring an
# already-restored record), or because the caller supplies an idempotency key
# that a replay is recognised by (recording a payment).
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

# Removes a record or reverses a financial entry. Most of our deletes are soft
# (recoverable from trash), but they still take the record out of every normal
# view, which is what this hint is warning about.
DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)

# Sends something a customer can see, or moves money through a provider.
# Not idempotent and not undoable: the defining case is an email that has
# already been delivered. These are the tools that also ask for confirmation.
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
