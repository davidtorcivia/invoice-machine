"""Confirmation prompts for tools whose effects cannot be undone.

The question is asked through the SDK's resolver mechanism: a parameter
annotated `Annotated[T, Resolve(fn)]` is filled by running `fn` before the tool
body, and resolved parameters are stripped from the tool's input schema, so the
model never sees - or supplies - them. Declining aborts the call.

Returning `Elicit` to a client that never declared the elicitation capability
fails the call with `MISSING_REQUIRED_CLIENT_CAPABILITY`, so every resolver
checks first and proceeds unasked when the client cannot answer.
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

    Declining aborts the call upstream, but a client can accept the elicitation
    and still return `confirm: false`, which for these tools has to mean stop.
    """
    if not answer.confirm:
        raise ValueError(f"{action} was not confirmed.")
