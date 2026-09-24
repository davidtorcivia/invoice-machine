"""An invoice's client snapshot must stay historically stable."""

import pytest

from invoice_machine.service.clients import ClientService
from invoice_machine.service.invoices import InvoiceService


@pytest.mark.asyncio
async def test_update_invoice_does_not_resnapshot_client(db_session, client_record):
    """Editing the client must not overwrite the snapshot taken at creation."""
    invoice = await InvoiceService.create_invoice(
        db_session,
        client_id=client_record.id,
        items=[{"description": "x", "quantity": 1, "unit_price": "100"}],
    )
    assert invoice.client_name == "John Doe"

    await ClientService.update_client(
        db_session, client_record.id, name="Jane Smith", business_name="NewCo"
    )

    updated = await InvoiceService.update_invoice(db_session, invoice.id, status="paid")
    assert updated.client_name == "John Doe"
    assert updated.client_business == "Acme Corp"
