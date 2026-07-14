"""Reminder REST settings tests."""

import pytest


@pytest.mark.asyncio
async def test_reminder_settings_are_opt_in(test_client):
    response = await test_client.get("/api/reminders/settings")
    assert response.status_code == 200
    assert response.json()["reminders_enabled"] is False


@pytest.mark.asyncio
async def test_reminder_settings_validate_timezone_and_offsets(test_client):
    invalid = await test_client.put(
        "/api/reminders/settings", json={"business_timezone": "Not/A_Zone"}
    )
    assert invalid.status_code == 400

    updated = await test_client.put(
        "/api/reminders/settings",
        json={
            "reminders_enabled": True,
            "business_timezone": "America/New_York",
            "reminder_offsets": [-5, 0, 5],
            "reminder_send_hour": 10,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["reminder_offsets"] == [-5, 0, 5]
    assert updated.json()["reminder_send_hour"] == 10
