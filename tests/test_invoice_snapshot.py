"""An invoice's client snapshot must stay historically stable."""

import pytest

from invoice_machine.services import ClientService, InvoiceService


@pytest.mark.asyncio
async def test_update_invoice_does_not_resnapshot_client(db_session, test_client):
    """Editing the client must not overwrite the snapshot taken at creation."""
    invoice = await InvoiceService.create_invoice(
        db_session,
        client_id=test_client.id,
        items=[{"description": "x", "quantity": 1, "unit_price": "100"}],
    )
    assert invoice.client_name == "John Doe"

    await ClientService.update_client(
        db_session, test_client.id, name="Jane Smith", business_name="NewCo"
    )

    updated = await InvoiceService.update_invoice(db_session, invoice.id, status="paid")
    assert updated.client_name == "John Doe"
    assert updated.client_business == "Acme Corp"
