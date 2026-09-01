"""Request ids, access logging, and the system status endpoint."""

import logging

import pytest

from invoice_machine.observability import RequestIdFilter, request_id_var, run_job


@pytest.mark.asyncio
async def test_request_id_is_generated_and_echoed(test_client):
    response = await test_client.get("/api/clients")
    generated = response.headers["x-request-id"]
    assert len(generated) == 16

    response = await test_client.get("/api/clients", headers={"X-Request-ID": "trace-abc.1"})
    assert response.headers["x-request-id"] == "trace-abc.1"

    response = await test_client.get(
        "/api/clients", headers={"X-Request-ID": "bad id\n" + "x" * 80}
    )
    assert response.headers["x-request-id"] != "bad id\n" + "x" * 80


@pytest.mark.asyncio
async def test_unauthenticated_rejections_still_carry_an_id():
    from httpx import ASGITransport, AsyncClient

    from invoice_machine.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/clients")
    assert response.status_code == 401
    assert response.headers["x-request-id"]


def test_log_records_carry_the_current_id():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    RequestIdFilter().filter(record)
    assert record.request_id == "-"
    token = request_id_var.set("req-1")
    try:
        RequestIdFilter().filter(record)
        assert record.request_id == "req-1"
    finally:
        request_id_var.reset(token)


@pytest.mark.asyncio
async def test_run_job_records_success_and_failure():
    jobs: dict = {}
    seen: list[str] = []

    async def ok():
        seen.append(request_id_var.get())

    async def boom():
        raise RuntimeError("smtp down")

    await run_job(jobs, "Reminders", ok)
    assert jobs["Reminders"]["runs"] == 1
    assert jobs["Reminders"]["last_ok_at"]
    assert jobs["Reminders"]["last_error"] is None
    assert seen[0].startswith("job-")
    assert request_id_var.get() == "-"

    with pytest.raises(RuntimeError):
        await run_job(jobs, "Reminders", boom)
    assert jobs["Reminders"] == {
        **jobs["Reminders"],
        "runs": 2,
        "failures": 1,
        "last_error": "RuntimeError: smtp down",
    }
    assert jobs["Reminders"]["last_duration_ms"] >= 0


@pytest.mark.asyncio
async def test_system_status_shape_and_auth(test_client):
    from httpx import ASGITransport, AsyncClient

    from invoice_machine.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        assert (await anon.get("/api/system/status")).status_code == 401

    app.state.jobs["Overdue check"] = {"runs": 1, "failures": 0, "last_error": None}
    body = (await test_client.get("/api/system/status")).json()
    assert body["version"]
    assert body["environment"] == "development"
    assert body["uptime_seconds"] >= 0
    assert body["scheduler"]["active"] is False
    assert body["scheduler"]["jobs"]["Overdue check"]["runs"] == 1

    health = (await test_client.get("/health")).json()
    assert health["scheduler"] == "standby"
