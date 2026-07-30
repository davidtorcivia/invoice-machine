"""MCP prompts: the handful of jobs this app actually gets used for.

A prompt is a user-invoked starting point - the slash commands a client shows in
its picker. These are deliberately few. A prompt earns its place only if it
encodes something a user would otherwise have to remember to say: which tool to
reach for, what to check first, what not to do.

Each one is written to leave the irreversible step to the user. "Draft", "list",
"propose" - none of them tell the model to send anything on its own initiative,
because sending is the one action here that cannot be taken back.
"""

from __future__ import annotations

from .context import mcp


@mcp.prompt(
    name="draft_invoice",
    title="Draft an invoice",
    description="Draft a new invoice for a client, matching their past invoices.",
)
def draft_invoice(client: str, work: str = "") -> str:
    """Draft an invoice, using the client's history to match rates and wording."""
    described = f" The work to bill: {work}." if work.strip() else ""
    return (
        f"Draft a new invoice for {client}.{described}\n\n"
        "Before writing it:\n"
        f"1. Find {client} with the search or list_clients tool, and confirm you "
        "have the right one if several match.\n"
        "2. Call get_client_invoice_context for their recent invoices, and match "
        "the rates, line-item wording, currency, and payment terms they have "
        "been billed with before.\n"
        "3. Check the business profile for defaults where the client has none.\n\n"
        "Then create the invoice as a draft and show me what you have written. "
        "Do not email it - I will review it first."
    )


@mcp.prompt(
    name="chase_overdue",
    title="Chase overdue invoices",
    description="Review what is overdue and propose reminders, without sending.",
)
def chase_overdue() -> str:
    """Triage the overdue list and propose what to send."""
    return (
        "Help me chase what I am owed.\n\n"
        "1. Read the invoices://outstanding resource, or list invoices with "
        "status overdue.\n"
        "2. Group them by client and tell me: who owes what, how many days "
        "overdue each invoice is, and the total outstanding per currency.\n"
        "3. For anything more than a week overdue, preview the reminder email "
        "with preview_invoice_reminder and show it to me.\n\n"
        "Do not send any reminders. Show me the list and the drafts, and I will "
        "tell you which to send."
    )


@mcp.prompt(
    name="month_end_summary",
    title="Month-end summary",
    description="Summarise revenue, outstanding balances, and top clients.",
)
def month_end_summary(period: str = "") -> str:
    """Pull the numbers for a month-end review."""
    window = period.strip() or "the month just ended"
    return (
        f"Give me a month-end summary for {window}.\n\n"
        "Use get_revenue_summary for the period, and get_client_lifetime_value "
        "for the top clients. Report:\n"
        "- Total invoiced and total paid, per currency\n"
        "- What is still outstanding, and how much of it is overdue\n"
        "- The largest clients by amount paid in the period\n"
        "- Anything that looks off: an unusually quiet month, a client who has "
        "stopped paying, invoices left sitting in draft\n\n"
        "Keep it short. Lead with the numbers, then anything I should act on."
    )
