"""Does the CSV export still work when the body is consumed after the handler returns?"""

import pytest


@pytest.mark.asyncio
async def test_large_export_streams_completely(test_client):
    """The generator holds a request-scoped session. If FastAPI tears that down
    before the body is consumed, the stream dies partway through."""
    for i in range(120):
        r = await test_client.post(
            "/api/invoices",
            json={"items": [{"description": f"Item {i}", "quantity": 1, "unit_price": 10}]},
        )
        assert r.status_code in (200, 201)

    resp = await test_client.get("/api/export/invoices.csv")
    assert resp.status_code == 200
    lines = resp.text.strip().splitlines()
    # header + 120 invoices
    assert len(lines) == 121, f"expected 121 lines, got {len(lines)}"
