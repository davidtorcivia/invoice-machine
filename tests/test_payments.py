"""Provider-neutral payment ledger tests."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from invoice_machine.database import Invoice, Payment, PaymentAdjustment, PaymentRefund
from invoice_machine.payments.base import ProviderEvent
from invoice_machine.payments.currency import from_minor_units, to_minor_units
from invoice_machine.service.analytics import revenue_summary
from invoice_machine.service.payments import PaymentService


@pytest.fixture
async def payable_invoice(db_session, test_client):
    invoice = Invoice(
        invoice_number="PAY-1",
        client_id=test_client.id,
        client_name=test_client.name,
        client_email=test_client.email,
        issue_date=test_client.created_at.date(),
        due_date=test_client.created_at.date(),
        currency_code="USD",
        subtotal=Decimal("100.00"),
        total=Decimal("100.00"),
        status="sent",
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)
    return invoice


@pytest.mark.asyncio
async def test_partial_then_full_manual_payment(db_session, payable_invoice):
    first = await PaymentService.record_manual_payment(
        db_session, payable_invoice.id, "40.00", notes="Bank transfer"
    )
    await db_session.refresh(payable_invoice)
    assert first.amount == Decimal("40.00")
    assert payable_invoice.status == "partially_paid"

    summary = await PaymentService.payment_summary(db_session, payable_invoice)
    assert summary["paid"] == Decimal("40.00")
    assert summary["outstanding"] == Decimal("60.00")

    await PaymentService.record_manual_payment(db_session, payable_invoice.id, "60.00")
    await db_session.refresh(payable_invoice)
    assert payable_invoice.status == "paid"
    assert payable_invoice.paid_at is not None


@pytest.mark.asyncio
async def test_overpayment_is_rejected(db_session, payable_invoice):
    with pytest.raises(ValueError, match="exceeds outstanding"):
        await PaymentService.record_manual_payment(db_session, payable_invoice.id, "100.01")


@pytest.mark.asyncio
async def test_refund_reopens_invoice(db_session, payable_invoice):
    payment = await PaymentService.record_manual_payment(
        db_session, payable_invoice.id, "100.00"
    )
    await PaymentService.refund_payment(
        db_session,
        payment.id,
        "25.00",
        idempotency_key="manual-refund-test-1",
    )
    await db_session.refresh(payable_invoice)
    assert payable_invoice.status == "partially_paid"

    summary = await PaymentService.payment_summary(db_session, payable_invoice)
    assert summary["paid"] == Decimal("75.00")
    assert summary["refunded"] == Decimal("25.00")
    assert summary["outstanding"] == Decimal("25.00")


@pytest.mark.asyncio
async def test_refund_rejects_stale_concurrent_balance_claim(
    db_session, session_maker, payable_invoice
):
    payment = await PaymentService.record_manual_payment(
        db_session, payable_invoice.id, "100.00"
    )
    payment_id = payment.id

    async with session_maker() as first_session, session_maker() as stale_session:
        await first_session.get(Payment, payment_id)
        await stale_session.get(Payment, payment_id)

        await PaymentService.refund_payment(
            first_session,
            payment_id,
            "60.00",
            idempotency_key="manual-refund-claim-1",
        )
        with pytest.raises(ValueError, match="between 0.01 and 40.00"):
            await PaymentService.refund_payment(
                stale_session,
                payment_id,
                "60.00",
                idempotency_key="manual-refund-claim-2",
            )

    db_session.expire_all()
    updated = await db_session.get(Payment, payment_id)
    refunds = (
        await db_session.execute(
            select(PaymentRefund).where(PaymentRefund.payment_id == payment_id)
        )
    ).scalars().all()
    assert updated.refunded_amount == Decimal("60.00")
    assert len(refunds) == 1


@pytest.mark.asyncio
async def test_provider_payment_is_idempotent(db_session, payable_invoice):
    first = await PaymentService.record_provider_payment(
        db_session,
        payable_invoice.id,
        amount="100.00",
        currency_code="usd",
        provider="stripe",
        status="processing",
        provider_payment_id="pi_123",
        provider_checkout_id="cs_123",
    )
    second = await PaymentService.record_provider_payment(
        db_session,
        payable_invoice.id,
        amount="100.00",
        currency_code="USD",
        provider="stripe",
        status="succeeded",
        provider_payment_id="pi_123",
        provider_checkout_id="cs_123",
    )
    assert first.id == second.id
    assert second.status == "succeeded"
    assert len(await PaymentService.list_payments(db_session, payable_invoice.id)) == 1


@pytest.mark.asyncio
async def test_async_success_uses_settlement_event_time(db_session, payable_invoice):
    checkout_time = datetime(2025, 6, 20, 12, tzinfo=UTC)
    settlement_time = datetime(2025, 7, 10, 12, tzinfo=UTC)
    await PaymentService.record_provider_payment(
        db_session,
        payable_invoice.id,
        amount="100.00",
        currency_code="USD",
        provider="stripe",
        status="processing",
        provider_payment_id="pi_async",
        provider_checkout_id="cs_async",
        occurred_at=checkout_time,
    )
    event = ProviderEvent(
        id="evt_async_success",
        type="checkout.session.async_payment_succeeded",
        occurred_at=settlement_time,
        data={
            "id": "cs_async",
            "payment_intent": "pi_async",
            "amount_total": 10000,
            "currency": "usd",
            "metadata": {
                "invoice_id": str(payable_invoice.id),
                "expected_amount_minor": "10000",
                "currency_code": "USD",
            },
        },
    )

    await PaymentService.process_provider_event(db_session, "stripe", event, "d" * 64)
    payment = (await PaymentService.list_payments(db_session, payable_invoice.id))[0]

    assert payment.status == "succeeded"
    assert payment.occurred_at.replace(tzinfo=UTC) == settlement_time


@pytest.mark.asyncio
async def test_late_checkout_events_do_not_downgrade_success(db_session, payable_invoice):
    metadata = {
        "invoice_id": str(payable_invoice.id),
        "expected_amount_minor": "10000",
        "currency_code": "USD",
    }
    succeeded = ProviderEvent(
        id="evt_success_first",
        type="checkout.session.async_payment_succeeded",
        data={
            "id": "cs_out_of_order",
            "payment_intent": "pi_out_of_order",
            "amount_total": 10000,
            "currency": "usd",
            "metadata": metadata,
        },
    )
    late_completed = ProviderEvent(
        id="evt_completed_late",
        type="checkout.session.completed",
        data={
            "id": "cs_out_of_order",
            "payment_intent": "pi_out_of_order",
            "payment_status": "unpaid",
            "amount_total": 10000,
            "currency": "usd",
            "metadata": metadata,
        },
    )
    late_failed = ProviderEvent(
        id="evt_failed_late",
        type="checkout.session.async_payment_failed",
        data={
            "id": "cs_out_of_order",
            "payment_intent": "pi_out_of_order",
            "amount_total": 10000,
            "currency": "usd",
            "metadata": metadata,
        },
    )

    await PaymentService.process_provider_event(db_session, "stripe", succeeded, "1" * 64)
    await PaymentService.process_provider_event(db_session, "stripe", late_completed, "2" * 64)
    await PaymentService.process_provider_event(db_session, "stripe", late_failed, "3" * 64)
    payment = (await PaymentService.list_payments(db_session, payable_invoice.id))[0]

    assert payment.status == "succeeded"
    assert payable_invoice.status == "paid"


@pytest.mark.asyncio
async def test_provider_currency_mismatch_is_rejected(db_session, payable_invoice):
    with pytest.raises(ValueError, match="currency"):
        await PaymentService.record_provider_payment(
            db_session,
            payable_invoice.id,
            amount="100.00",
            currency_code="EUR",
            provider="stripe",
            status="succeeded",
            provider_payment_id="pi_bad",
        )


@pytest.mark.asyncio
async def test_payment_token_is_optional_and_rotatable(db_session, payable_invoice):
    assert payable_invoice.payment_token is None
    enabled = await PaymentService.set_online_payment_enabled(
        db_session, payable_invoice.id, True
    )
    original = enabled.payment_token
    assert enabled.online_payment_enabled == 1
    assert original and len(original) > 40

    rotated = await PaymentService.set_online_payment_enabled(
        db_session, payable_invoice.id, True, rotate_token=True
    )
    assert rotated.payment_token != original


def test_currency_minor_units_are_exact():
    assert to_minor_units(Decimal("10.25"), "USD") == 1025
    assert from_minor_units(1025, "USD") == Decimal("10.25")
    assert to_minor_units(Decimal("100"), "JPY") == 100
    assert to_minor_units(Decimal("1.234"), "KWD") == 1234
    with pytest.raises(ValueError, match="0 decimal places"):
        to_minor_units(Decimal("1.01"), "JPY")


@pytest.mark.asyncio
async def test_verified_provider_event_is_replay_safe(db_session, payable_invoice):
    event = ProviderEvent(
        id="evt_123",
        type="checkout.session.completed",
        data={
            "id": "cs_123",
            "payment_intent": "pi_123",
            "payment_status": "paid",
            "amount_total": 10000,
            "currency": "usd",
            "metadata": {
                "invoice_id": str(payable_invoice.id),
                "expected_amount_minor": "10000",
                "currency_code": "USD",
            },
        },
    )
    first = await PaymentService.process_provider_event(
        db_session, "stripe", event, "a" * 64
    )
    duplicate = await PaymentService.process_provider_event(
        db_session, "stripe", event, "a" * 64
    )
    await db_session.refresh(payable_invoice)
    assert first == {"processed": True, "duplicate": False}
    assert duplicate == {"processed": False, "duplicate": True}
    assert payable_invoice.status == "paid"
    assert len(await PaymentService.list_payments(db_session, payable_invoice.id)) == 1


@pytest.mark.asyncio
async def test_delayed_checkout_on_cancelled_invoice_needs_review(db_session, payable_invoice):
    payable_invoice.status = "cancelled"
    await db_session.commit()
    event = ProviderEvent(
        id="evt_cancelled",
        type="checkout.session.completed",
        data={
            "id": "cs_cancelled",
            "payment_intent": "pi_cancelled",
            "payment_status": "paid",
            "amount_total": 10000,
            "currency": "usd",
            "metadata": {
                "invoice_id": str(payable_invoice.id),
                "expected_amount_minor": "10000",
                "currency_code": "USD",
            },
        },
    )

    await PaymentService.process_provider_event(db_session, "stripe", event, "b" * 64)
    await db_session.refresh(payable_invoice)
    payments = await PaymentService.list_payments(db_session, payable_invoice.id)

    assert payable_invoice.status == "cancelled"
    assert payments[0].status == "needs_review"


@pytest.mark.asyncio
async def test_provider_refund_records_event_date(db_session, payable_invoice):
    payment = await PaymentService.record_provider_payment(
        db_session,
        payable_invoice.id,
        amount="100.00",
        currency_code="USD",
        provider="stripe",
        status="succeeded",
        provider_payment_id="pi_refund_date",
        provider_checkout_id="cs_refund_date",
        occurred_at=datetime(2025, 6, 20, 12, tzinfo=UTC),
    )
    refund_time = datetime(2025, 7, 10, 12, tzinfo=UTC)
    event = ProviderEvent(
        id="evt_refund_date",
        type="charge.refunded",
        occurred_at=refund_time,
        data={
            "payment_intent": payment.provider_payment_id,
            "amount_refunded": 2500,
        },
    )

    await PaymentService.process_provider_event(db_session, "stripe", event, "c" * 64)
    refund = (
        await db_session.execute(
            select(PaymentRefund).where(PaymentRefund.payment_id == payment.id)
        )
    ).scalar_one()

    assert refund.amount == Decimal("25.00")
    assert refund.occurred_at.replace(tzinfo=UTC) == refund_time


@pytest.mark.asyncio
async def test_dispute_and_reversal_are_dated_cash_adjustments(db_session, payable_invoice):
    payment_time = datetime(2025, 6, 20, 12, tzinfo=UTC)
    opened_time = datetime(2025, 7, 10, 12, tzinfo=UTC)
    won_time = datetime(2025, 8, 5, 12, tzinfo=UTC)
    payment = await PaymentService.record_provider_payment(
        db_session,
        payable_invoice.id,
        amount="100.00",
        currency_code="USD",
        provider="stripe",
        status="succeeded",
        provider_payment_id="pi_dispute",
        occurred_at=payment_time,
    )
    opened = ProviderEvent(
        id="evt_dispute_opened",
        type="charge.dispute.created",
        occurred_at=opened_time,
        data={"payment_intent": payment.provider_payment_id, "amount": 4000},
    )
    won = ProviderEvent(
        id="evt_dispute_won",
        type="charge.dispute.closed",
        occurred_at=won_time,
        data={
            "payment_intent": payment.provider_payment_id,
            "amount": 4000,
            "status": "won",
        },
    )

    await PaymentService.process_provider_event(db_session, "stripe", opened, "e" * 64)
    july = await revenue_summary(db_session, date(2025, 7, 1), date(2025, 7, 31))
    summary = await PaymentService.payment_summary(db_session, payable_invoice)
    assert july["totals"]["paid"] == "-40.00"
    assert summary["paid"] == Decimal("60.00")
    assert summary["disputed"] == Decimal("40.00")

    await PaymentService.process_provider_event(db_session, "stripe", won, "f" * 64)
    june = await revenue_summary(db_session, date(2025, 6, 1), date(2025, 6, 30))
    august = await revenue_summary(db_session, date(2025, 8, 1), date(2025, 8, 31))
    adjustments = (
        await db_session.execute(
            select(PaymentAdjustment).where(PaymentAdjustment.payment_id == payment.id)
        )
    ).scalars().all()

    assert june["totals"]["paid"] == "100.00"
    assert august["totals"]["paid"] == "40.00"
    assert [adjustment.amount for adjustment in adjustments] == [
        Decimal("-40.00"),
        Decimal("40.00"),
    ]


@pytest.mark.asyncio
async def test_dispute_preserves_needs_review_state(db_session, payable_invoice):
    payment = await PaymentService.record_provider_payment(
        db_session,
        payable_invoice.id,
        amount="100.00",
        currency_code="USD",
        provider="stripe",
        status="needs_review",
        provider_payment_id="pi_review_dispute",
        allow_ineligible_invoice=True,
    )
    opened = ProviderEvent(
        id="evt_review_dispute_opened",
        type="charge.dispute.created",
        data={"payment_intent": payment.provider_payment_id, "amount": 10000},
    )
    won = ProviderEvent(
        id="evt_review_dispute_won",
        type="charge.dispute.closed",
        data={
            "payment_intent": payment.provider_payment_id,
            "amount": 10000,
            "status": "won",
        },
    )

    await PaymentService.process_provider_event(db_session, "stripe", opened, "4" * 64)
    await PaymentService.process_provider_event(db_session, "stripe", won, "5" * 64)
    await db_session.refresh(payment)
    summary = await PaymentService.payment_summary(db_session, payable_invoice)

    assert payment.status == "needs_review"
    assert payment.dispute_status is None
    assert summary["paid"] == Decimal("0.00")
