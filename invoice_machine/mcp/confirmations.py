"""Confirmation prompts for tools whose effects leave the building.

Most tools here are recoverable: a soft-deleted invoice sits in the trash, a
wrong field can be updated again. A handful are not. Once an invoice email
reaches a client's inbox there is no unsend, and a refund moves real money.
Those tools ask first.

The question is asked through the SDK's resolver mechanism: a parameter
annotated `Annotated[T, Resolve(fn)]` is filled by running `fn` before the tool
body, and `fn` returns an `Elicit(...)` marker to have the framework ask the
client. Resolved parameters are stripped from the tool's input schema, so the
model never sees - or supplies - them.

Two properties of that mechanism are why this is worth doing statelessly:

- The transport is chosen from the negotiated protocol version. On 2026-07-28
  the question rides an `InputRequiredResult` and the client retries the call
  with its answer; on older revisions the SDK falls back to a standalone
  server-to-client request. We write it once.
- Answers travel in `request_state`, and only questions actually asked are
  recorded, so a retried call does not re-ask something already answered.

Declining aborts the call: with an unwrapped `Annotated[T, Resolve(fn)]`
consumer, the framework raises rather than running the tool body.

**Graceful degradation matters here.** If a resolver returns `Elicit` to a
client that never declared the elicitation capability, the SDK fails the call
with `MISSING_REQUIRED_CLIENT_CAPABILITY`. Silently breaking `send_invoice_email`
for every client that cannot be asked would be worse than not asking, so each
resolver checks first and proceeds unasked when the client cannot answer. Those
clients still have the tool annotations (`openWorldHint`, non-idempotent) to
drive their own approval UI.
"""

from __future__ import annotations

from mcp.server.mcpserver import Context, Elicit
from pydantic import BaseModel, Field


class Confirmation(BaseModel):
    """A yes/no answer. Elicitation schemas may only use primitive types."""

    confirm: bool = Field(
        default=False,
        description="Confirm this action. It cannot be undone.",
    )


def can_elicit(ctx: Context) -> bool:
    """Whether this client declared it can answer a form elicitation.

    Mirrors the SDK's own check: a bare `elicitation: {}` predates elicitation
    modes and counts as form support, but a url-only declaration does not.
    """
    capabilities = ctx.client_capabilities
    elicitation = capabilities.elicitation if capabilities is not None else None
    if elicitation is None:
        return False
    return elicitation.form is not None or elicitation.url is None


def confirmed(ctx: Context, message: str) -> Confirmation | Elicit[Confirmation]:
    """Ask the client to confirm, or proceed unasked if it cannot be asked."""
    if not can_elicit(ctx):
        return Confirmation(confirm=True)
    return Elicit(message, Confirmation)


def ensure_confirmed(answer: Confirmation, action: str) -> None:
    """Reject an accepted-but-negative answer.

    Declining is already handled upstream - the framework aborts the call - but
    a client can accept the elicitation and still return `confirm: false`, and
    for these tools that has to mean stop.
    """
    if not answer.confirm:
        raise ValueError(f"{action} was not confirmed.")
