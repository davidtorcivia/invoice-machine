"""Analytics service: currency-aware aggregation shared by REST and MCP.

Money is never summed across currencies. Aggregates are grouped by
``currency_code``; results expose a single "primary" currency at the top level
plus a ``by_currency`` breakdown so multi-currency data is never collapsed or
mislabeled. Both the REST endpoints and the MCP tools call these functions so
the two surfaces cannot drift.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import Integer, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_machine.database import (
    BusinessProfile,
    Invoice,
    Payment,
    PaymentAdjustment,
    PaymentRefund,
)
from invoice_machine.service.clients import ClientService
from invoice_machine.service.common import BILLED_STATUSES, format_currency, quantize_money
from invoice_machine.utils import utc_now

RECEIVED_PAYMENT_STATUSES = [
    "succeeded",
    "partially_refunded",
    "refunded",
]


def _net_paid_for_invoice():
    """Correlated current payment total, net of refunds and disputes."""
    return func.coalesce(
        select(
            func.sum(
                case(
                    (
                        Payment.status.in_(RECEIVED_PAYMENT_STATUSES),
                        Payment.amount
                        - func.coalesce(Payment.refunded_amount, 0)
                        - func.coalesce(Payment.disputed_amount, 0),
                    ),
                    else_=0,
                )
            )
        )
        .where(Payment.invoice_id == Invoice.id)
        .correlate(Invoice)
        .scalar_subquery(),
        0,
    )


async def default_currency(session: AsyncSession) -> str:
    """Return the business default currency (fallback USD)."""
    profile = await BusinessProfile.get(session)
    return (profile.default_currency_code if profile else None) or "USD"


def pick_primary_currency(per_currency: dict[str, dict], default_cur: str) -> str:
    """Choose the headline currency: the default if it has activity, else the
    most active currency present, else the default."""
    if default_cur in per_currency:
        return default_cur
    if per_currency:
        return max(per_currency, key=lambda c: per_currency[c].get("invoice_count", 0))
    return default_cur


async def dashboard_summary(session: AsyncSession) -> dict:
    """Dashboard totals (outstanding, paid-this-month) grouped by currency."""
    today = utc_now().date()
    month_start = datetime(today.year, today.month, 1)
    if today.month == 12:
        next_month_start = datetime(today.year + 1, 1, 1)
    else:
        next_month_start = datetime(today.year, today.month + 1, 1)

    base_filter = and_(
        Invoice.document_type == "invoice",
        Invoice.deleted_at.is_(None),
    )
    net_paid = _net_paid_for_invoice()
    balance = func.max(Invoice.total - net_paid, 0)

    money_rows = (
        await session.execute(
            select(
                Invoice.currency_code.label("currency"),
                func.coalesce(
                    func.sum(
                        case(
                            (Invoice.status.in_(["sent", "overdue", "partially_paid"]), balance),
                            else_=0,
                        )
                    ),
                    0,
                ).label("outstanding"),
                func.count(Invoice.id).label("invoice_count"),
            )
            .where(base_filter)
            .group_by(Invoice.currency_code)
        )
    ).all()

    payment_rows = (
        await session.execute(
            select(
                Payment.currency_code.label("currency"),
                func.coalesce(
                    func.sum(Payment.amount), 0
                ).label("paid_this_month"),
            )
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(
                base_filter,
                Payment.status.in_(RECEIVED_PAYMENT_STATUSES),
                Payment.occurred_at >= month_start,
                Payment.occurred_at < next_month_start,
            )
            .group_by(Payment.currency_code)
        )
    ).all()
    received_by_currency = {
        row.currency: quantize_money(row.paid_this_month) for row in payment_rows
    }
    refund_rows = (
        await session.execute(
            select(
                PaymentRefund.currency_code.label("currency"),
                func.coalesce(func.sum(PaymentRefund.amount), 0).label("refunded_this_month"),
            )
            .join(Payment, Payment.id == PaymentRefund.payment_id)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(
                base_filter,
                PaymentRefund.occurred_at >= month_start,
                PaymentRefund.occurred_at < next_month_start,
            )
            .group_by(PaymentRefund.currency_code)
        )
    ).all()
    refunded_by_currency = {
        row.currency: quantize_money(row.refunded_this_month) for row in refund_rows
    }
    adjustment_rows = (
        await session.execute(
            select(
                PaymentAdjustment.currency_code.label("currency"),
                func.coalesce(func.sum(PaymentAdjustment.amount), 0).label("adjustments"),
            )
            .join(Payment, Payment.id == PaymentAdjustment.payment_id)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(
                base_filter,
                Payment.status.in_(RECEIVED_PAYMENT_STATUSES),
                PaymentAdjustment.occurred_at >= month_start,
                PaymentAdjustment.occurred_at < next_month_start,
            )
            .group_by(PaymentAdjustment.currency_code)
        )
    ).all()
    adjustments_by_currency = {
        row.currency: quantize_money(row.adjustments) for row in adjustment_rows
    }
    paid_by_currency = {
        currency: received_by_currency.get(currency, Decimal("0.00"))
        - refunded_by_currency.get(currency, Decimal("0.00"))
        + adjustments_by_currency.get(currency, Decimal("0.00"))
        for currency in (
            received_by_currency.keys()
            | refunded_by_currency.keys()
            | adjustments_by_currency.keys()
        )
    }

    counts = (
        await session.execute(
            select(
                func.count(case((Invoice.status == "draft", 1))).label("draft_count"),
                func.count(Invoice.id).label("invoice_count"),
            ).where(base_filter)
        )
    ).one()

    default_cur = await default_currency(session)
    per_currency = {
        (row.currency or default_cur): {
            "outstanding": quantize_money(row.outstanding),
            "paid_this_month": paid_by_currency.get(
                row.currency or default_cur, Decimal("0.00")
            ),
            "invoice_count": row.invoice_count or 0,
        }
        for row in money_rows
    }
    for currency, paid in paid_by_currency.items():
        per_currency.setdefault(
            currency,
            {"outstanding": Decimal("0.00"), "invoice_count": 0},
        )["paid_this_month"] = paid
    primary = pick_primary_currency(per_currency, default_cur)
    prim = per_currency.get(
        primary, {"outstanding": Decimal("0.00"), "paid_this_month": Decimal("0.00")}
    )

    return {
        "currency": primary,
        "total_outstanding": str(prim["outstanding"]),
        "total_outstanding_formatted": format_currency(prim["outstanding"], primary),
        "paid_this_month": str(prim["paid_this_month"]),
        "paid_this_month_formatted": format_currency(prim["paid_this_month"], primary),
        "draft_count": counts.draft_count or 0,
        "invoice_count": counts.invoice_count or 0,
        "by_currency": {
            cur: {
                "outstanding": str(vals["outstanding"]),
                "outstanding_formatted": format_currency(vals["outstanding"], cur),
                "paid_this_month": str(vals["paid_this_month"]),
                "paid_this_month_formatted": format_currency(vals["paid_this_month"], cur),
            }
            for cur, vals in per_currency.items()
        },
        "other_currencies": [c for c in per_currency if c != primary],
    }


def _bucket_totals(vals: dict, cur: str) -> dict:
    invoiced = vals.get("invoiced", Decimal("0.00"))
    paid = vals.get("paid", Decimal("0.00"))
    draft = vals.get("draft", Decimal("0.00"))
    outstanding = vals.get("outstanding", Decimal("0.00"))
    overdue = vals.get("overdue", Decimal("0.00"))
    return {
        "invoiced": str(invoiced),
        "invoiced_formatted": format_currency(invoiced, cur),
        "paid": str(paid),
        "paid_formatted": format_currency(paid, cur),
        "outstanding": str(outstanding),
        "outstanding_formatted": format_currency(outstanding, cur),
        "draft": str(draft),
        "draft_formatted": format_currency(draft, cur),
        "overdue": str(overdue),
        "overdue_formatted": format_currency(overdue, cur),
        "invoice_count": vals.get("invoice_count", 0),
    }


async def revenue_summary(
    session: AsyncSession,
    from_date_parsed: date,
    to_date_parsed: date,
    group_by: str = "month",
) -> dict:
    """Revenue summary grouped by currency, with period breakdown.

    Invoice-scoped metrics (invoiced/draft) use the invoice issue date; paid
    metrics use the date funds were received. Point-in-time metrics
    (outstanding/overdue) reflect current state across all invoices.
    Overdue = status "overdue" OR (status "sent" AND past due).
    """
    today = utc_now().date()

    period_filter = and_(
        Invoice.document_type == "invoice",
        Invoice.issue_date >= from_date_parsed,
        Invoice.issue_date <= to_date_parsed,
        Invoice.deleted_at.is_(None),
    )
    global_filter = and_(
        Invoice.document_type == "invoice",
        Invoice.deleted_at.is_(None),
    )
    payment_period_filter = and_(
        Invoice.document_type == "invoice",
        Invoice.deleted_at.is_(None),
        Payment.status.in_(RECEIVED_PAYMENT_STATUSES),
        Payment.occurred_at >= datetime.combine(from_date_parsed, time.min),
        Payment.occurred_at < datetime.combine(to_date_parsed + timedelta(days=1), time.min),
    )
    refund_period_filter = and_(
        Invoice.document_type == "invoice",
        Invoice.deleted_at.is_(None),
        PaymentRefund.occurred_at >= datetime.combine(from_date_parsed, time.min),
        PaymentRefund.occurred_at
        < datetime.combine(to_date_parsed + timedelta(days=1), time.min),
    )
    adjustment_period_filter = and_(
        Invoice.document_type == "invoice",
        Invoice.deleted_at.is_(None),
        Payment.status.in_(RECEIVED_PAYMENT_STATUSES),
        PaymentAdjustment.occurred_at >= datetime.combine(from_date_parsed, time.min),
        PaymentAdjustment.occurred_at
        < datetime.combine(to_date_parsed + timedelta(days=1), time.min),
    )
    net_paid = _net_paid_for_invoice()
    balance = func.max(Invoice.total - net_paid, 0)

    period_rows = (
        await session.execute(
            select(
                Invoice.currency_code.label("currency"),
                func.count(Invoice.id).label("invoice_count"),
                func.coalesce(
                    func.sum(
                        case((Invoice.status.in_(BILLED_STATUSES), Invoice.total), else_=0)
                    ),
                    0,
                ).label("total_invoiced"),
                func.coalesce(
                    func.sum(case((Invoice.status == "draft", Invoice.total), else_=0)), 0
                ).label("total_draft"),
            )
            .where(period_filter)
            .group_by(Invoice.currency_code)
        )
    ).all()

    payment_rows = (
        await session.execute(
            select(
                Payment.currency_code.label("currency"),
                func.coalesce(
                    func.sum(Payment.amount), 0
                ).label("total_paid"),
            )
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(payment_period_filter)
            .group_by(Payment.currency_code)
        )
    ).all()

    refund_rows = (
        await session.execute(
            select(
                PaymentRefund.currency_code.label("currency"),
                func.coalesce(func.sum(PaymentRefund.amount), 0).label("total_refunded"),
            )
            .join(Payment, Payment.id == PaymentRefund.payment_id)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(refund_period_filter)
            .group_by(PaymentRefund.currency_code)
        )
    ).all()

    adjustment_rows = (
        await session.execute(
            select(
                PaymentAdjustment.currency_code.label("currency"),
                func.coalesce(func.sum(PaymentAdjustment.amount), 0).label("adjustments"),
            )
            .join(Payment, Payment.id == PaymentAdjustment.payment_id)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(adjustment_period_filter)
            .group_by(PaymentAdjustment.currency_code)
        )
    ).all()

    is_effectively_overdue = or_(
        Invoice.status == "overdue",
        and_(Invoice.status == "sent", Invoice.due_date < today),
    )

    outstanding_rows = (
        await session.execute(
            select(
                Invoice.currency_code.label("currency"),
                func.coalesce(
                    func.sum(
                        case(
                            (Invoice.status.in_(["sent", "overdue", "partially_paid"]), balance),
                            else_=0,
                        )
                    ),
                    0,
                ).label("total_outstanding"),
                func.coalesce(
                    func.sum(case((is_effectively_overdue, balance), else_=0)), 0
                ).label("total_overdue"),
            )
            .where(global_filter)
            .group_by(Invoice.currency_code)
        )
    ).all()

    default_cur = await default_currency(session)

    per_currency: dict[str, dict] = {}
    for row in period_rows:
        cur = row.currency or default_cur
        bucket = per_currency.setdefault(cur, {})
        bucket["invoice_count"] = row.invoice_count or 0
        bucket["invoiced"] = quantize_money(row.total_invoiced)
        bucket["draft"] = quantize_money(row.total_draft)
    for row in payment_rows:
        cur = row.currency or default_cur
        bucket = per_currency.setdefault(cur, {})
        bucket["paid"] = quantize_money(row.total_paid)
    for row in refund_rows:
        cur = row.currency or default_cur
        bucket = per_currency.setdefault(cur, {})
        bucket["paid"] = quantize_money(
            bucket.get("paid", Decimal("0.00")) - row.total_refunded
        )
    for row in adjustment_rows:
        cur = row.currency or default_cur
        bucket = per_currency.setdefault(cur, {})
        bucket["paid"] = quantize_money(
            bucket.get("paid", Decimal("0.00")) + row.adjustments
        )
    for row in outstanding_rows:
        cur = row.currency or default_cur
        bucket = per_currency.setdefault(cur, {})
        bucket["outstanding"] = quantize_money(row.total_outstanding)
        bucket["overdue"] = quantize_money(row.total_overdue)

    primary = pick_primary_currency(per_currency, default_cur)
    totals = _bucket_totals(per_currency.get(primary, {}), primary)

    if group_by == "month":
        invoice_period_expr = func.strftime("%Y-%m", Invoice.issue_date)
        payment_period_expr = func.strftime("%Y-%m", Payment.occurred_at)
        refund_period_expr = func.strftime("%Y-%m", PaymentRefund.occurred_at)
        adjustment_period_expr = func.strftime("%Y-%m", PaymentAdjustment.occurred_at)
    elif group_by == "quarter":
        invoice_period_expr = func.printf(
            "%d-Q%d",
            func.cast(func.strftime("%Y", Invoice.issue_date), Integer),
            (func.cast(func.strftime("%m", Invoice.issue_date), Integer) - 1) / 3 + 1,
        )
        payment_period_expr = func.printf(
            "%d-Q%d",
            func.cast(func.strftime("%Y", Payment.occurred_at), Integer),
            (func.cast(func.strftime("%m", Payment.occurred_at), Integer) - 1) / 3 + 1,
        )
        refund_period_expr = func.printf(
            "%d-Q%d",
            func.cast(func.strftime("%Y", PaymentRefund.occurred_at), Integer),
            (func.cast(func.strftime("%m", PaymentRefund.occurred_at), Integer) - 1) / 3 + 1,
        )
        adjustment_period_expr = func.printf(
            "%d-Q%d",
            func.cast(func.strftime("%Y", PaymentAdjustment.occurred_at), Integer),
            (func.cast(func.strftime("%m", PaymentAdjustment.occurred_at), Integer) - 1)
            / 3
            + 1,
        )
    else:  # year
        invoice_period_expr = func.strftime("%Y", Invoice.issue_date)
        payment_period_expr = func.strftime("%Y", Payment.occurred_at)
        refund_period_expr = func.strftime("%Y", PaymentRefund.occurred_at)
        adjustment_period_expr = func.strftime("%Y", PaymentAdjustment.occurred_at)

    invoice_breakdown_rows = (
        await session.execute(
            select(
                invoice_period_expr.label("period"),
                func.count(Invoice.id).label("count"),
                func.coalesce(
                    func.sum(
                        case((Invoice.status.in_(BILLED_STATUSES), Invoice.total), else_=0)
                    ),
                    0,
                ).label("invoiced"),
            )
            .where(and_(period_filter, Invoice.currency_code == primary))
            .group_by(invoice_period_expr)
        )
    ).all()

    payment_breakdown_rows = (
        await session.execute(
            select(
                payment_period_expr.label("period"),
                func.coalesce(
                    func.sum(Payment.amount), 0
                ).label("paid"),
            )
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(and_(payment_period_filter, Payment.currency_code == primary))
            .group_by(payment_period_expr)
        )
    ).all()

    refund_breakdown_rows = (
        await session.execute(
            select(
                refund_period_expr.label("period"),
                func.coalesce(func.sum(PaymentRefund.amount), 0).label("refunded"),
            )
            .join(Payment, Payment.id == PaymentRefund.payment_id)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(
                and_(refund_period_filter, PaymentRefund.currency_code == primary)
            )
            .group_by(refund_period_expr)
        )
    ).all()

    adjustment_breakdown_rows = (
        await session.execute(
            select(
                adjustment_period_expr.label("period"),
                func.coalesce(func.sum(PaymentAdjustment.amount), 0).label("adjustments"),
            )
            .join(Payment, Payment.id == PaymentAdjustment.payment_id)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(
                and_(
                    adjustment_period_filter,
                    PaymentAdjustment.currency_code == primary,
                )
            )
            .group_by(adjustment_period_expr)
        )
    ).all()

    breakdown_by_period = {
        row.period: {
            "invoiced": quantize_money(row.invoiced),
            "paid": Decimal("0.00"),
            "count": row.count,
        }
        for row in invoice_breakdown_rows
    }
    for row in payment_breakdown_rows:
        breakdown_by_period.setdefault(
            row.period,
            {"invoiced": Decimal("0.00"), "paid": Decimal("0.00"), "count": 0},
        )["paid"] = quantize_money(row.paid)
    for row in refund_breakdown_rows:
        values = breakdown_by_period.setdefault(
            row.period,
            {"invoiced": Decimal("0.00"), "paid": Decimal("0.00"), "count": 0},
        )
        values["paid"] = quantize_money(values["paid"] - row.refunded)
    for row in adjustment_breakdown_rows:
        values = breakdown_by_period.setdefault(
            row.period,
            {"invoiced": Decimal("0.00"), "paid": Decimal("0.00"), "count": 0},
        )
        values["paid"] = quantize_money(values["paid"] + row.adjustments)

    breakdown = [
        {
            "period": period,
            "invoiced": str(values["invoiced"]),
            "invoiced_formatted": format_currency(values["invoiced"], primary),
            "paid": str(values["paid"]),
            "paid_formatted": format_currency(values["paid"], primary),
            "count": values["count"],
        }
        for period, values in sorted(breakdown_by_period.items())
    ]

    return {
        "period": f"{from_date_parsed} to {to_date_parsed}",
        "currency": primary,
        "totals": totals,
        "by_currency": {cur: _bucket_totals(vals, cur) for cur, vals in per_currency.items()},
        "other_currencies": [c for c in per_currency if c != primary],
        "breakdown": breakdown,
    }


async def client_lifetime_values(
    session: AsyncSession,
    client_id: int | None = None,
    limit: int = 20,
) -> list[dict]:
    """Per-client lifetime value in the client's dominant currency."""
    stats = await ClientService.get_client_invoice_stats(
        session, client_id=client_id, limit=limit
    )
    return [
        {
            "client_id": stat["client_id"],
            "name": stat["name"],
            "email": stat["email"],
            "currency": stat["currency"],
            "total_invoiced": str(stat["total_invoiced"]),
            "total_invoiced_formatted": format_currency(stat["total_invoiced"], stat["currency"]),
            "total_paid": str(stat["total_paid"]),
            "total_paid_formatted": format_currency(stat["total_paid"], stat["currency"]),
            "invoice_count": stat["invoice_count"],
            "paid_invoice_count": stat["paid_invoice_count"],
            "by_currency": stat["by_currency"],
            "first_invoice": stat["first_invoice"].isoformat() if stat["first_invoice"] else None,
            "last_invoice": stat["last_invoice"].isoformat() if stat["last_invoice"] else None,
        }
        for stat in stats
    ]
