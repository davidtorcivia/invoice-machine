from unittest.mock import AsyncMock, patch

import pytest


class TestTrashEndpoints:
    """Tests for trash endpoints."""

    @pytest.mark.asyncio
    async def test_list_trash_empty(self, test_client):
        """Trash is empty initially."""
        response = await test_client.get("/api/trash")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_trash_with_items(self, test_client):
        """Lists both trashed clients and invoices."""
        # Create and delete a client
        client_response = await test_client.post(
            "/api/clients", json={"name": "Deleted Client"}
        )
        client_id = client_response.json()["id"]
        await test_client.delete(f"/api/clients/{client_id}")

        # Create and delete an invoice
        invoice_response = await test_client.post("/api/invoices", json={})
        invoice_id = invoice_response.json()["id"]
        await test_client.delete(f"/api/invoices/{invoice_id}")

        # List trash
        response = await test_client.get("/api/trash")
        assert response.status_code == 200

        items = response.json()
        assert len(items) == 2

        types = {item["type"] for item in items}
        assert "client" in types
        assert "invoice" in types

    @pytest.mark.asyncio
    async def test_empty_trash_keeps_trashed_client_with_live_invoice(self, test_client):
        """Emptying trash does not permanently delete clients still referenced by active invoices."""
        client_response = await test_client.post(
            "/api/clients", json={"name": "Protected Client"}
        )
        client_id = client_response.json()["id"]

        invoice_response = await test_client.post(
            "/api/invoices", json={"client_id": client_id}
        )
        invoice_id = invoice_response.json()["id"]

        await test_client.delete(f"/api/clients/{client_id}")

        response = await test_client.post("/api/trash/empty")
        assert response.status_code == 204

        restore_response = await test_client.post(f"/api/clients/{client_id}/restore")
        assert restore_response.status_code == 200

        invoice_get = await test_client.get(f"/api/invoices/{invoice_id}")
        assert invoice_get.status_code == 200


class TestBackupEndpoints:
    """Tests for backup endpoints."""

    @pytest.mark.asyncio
    async def test_download_backup_rejects_invalid_filename(self, test_client):
        """Backup download rejects traversal attempts before serving files."""
        import tempfile
        from pathlib import Path

        from invoice_machine.services import BackupService

        with tempfile.TemporaryDirectory() as tmpdir:
            service = BackupService(backup_dir=Path(tmpdir))
            with patch(
                "invoice_machine.api.backup.get_backup_service",
                AsyncMock(return_value=service),
            ):
                response = await test_client.get("/api/backups/download/..%5Csecret.db")

        assert response.status_code == 400


class TestRecurringEndpoints:
    """Tests for recurring invoice schedule endpoints."""

    @pytest.mark.asyncio
    async def test_list_recurring_empty(self, test_client):
        """List recurring schedules returns empty list initially."""
        response = await test_client.get("/api/recurring")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_create_recurring_schedule(self, test_client):
        """Create a recurring schedule."""
        # First create a client
        client_response = await test_client.post(
            "/api/clients", json={"name": "Recurring Client"}
        )
        client_id = client_response.json()["id"]

        # Create recurring schedule
        response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "Monthly Retainer",
                "frequency": "monthly",
                "schedule_day": 1,
                "line_items": [
                    {"description": "Retainer Fee", "quantity": 1, "unit_type": "qty", "unit_price": "500.00"}
                ],
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["id"] > 0
        assert data["name"] == "Monthly Retainer"
        assert data["frequency"] == "monthly"
        assert data["schedule_day"] == 1
        assert data["is_active"] == 1

    @pytest.mark.asyncio
    async def test_get_recurring_schedule(self, test_client):
        """Get a recurring schedule by ID."""
        # Create client and schedule
        client_response = await test_client.post(
            "/api/clients", json={"name": "Test Client"}
        )
        client_id = client_response.json()["id"]

        create_response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "Test Schedule",
                "frequency": "weekly",
                "schedule_day": 0,
            },
        )
        schedule_id = create_response.json()["id"]

        # Get it
        response = await test_client.get(f"/api/recurring/{schedule_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == schedule_id
        assert data["name"] == "Test Schedule"

    @pytest.mark.asyncio
    async def test_get_nonexistent_schedule(self, test_client):
        """Getting nonexistent schedule returns 404."""
        response = await test_client.get("/api/recurring/99999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_recurring_schedule(self, test_client):
        """Update a recurring schedule."""
        # Create client and schedule
        client_response = await test_client.post(
            "/api/clients", json={"name": "Test Client"}
        )
        client_id = client_response.json()["id"]

        create_response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "Original Name",
                "frequency": "monthly",
                "schedule_day": 15,
            },
        )
        schedule_id = create_response.json()["id"]

        # Update it
        response = await test_client.put(
            f"/api/recurring/{schedule_id}",
            json={"name": "Updated Name", "schedule_day": 20},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["schedule_day"] == 20

    @pytest.mark.asyncio
    async def test_update_recurring_schedule_rejects_invalid_weekly_day(self, test_client):
        """Weekly schedules reject out-of-range schedule_day values on update."""
        client_response = await test_client.post(
            "/api/clients", json={"name": "Weekly Client"}
        )
        client_id = client_response.json()["id"]

        create_response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "Weekly Schedule",
                "frequency": "weekly",
                "schedule_day": 1,
            },
        )
        schedule_id = create_response.json()["id"]

        response = await test_client.put(
            f"/api/recurring/{schedule_id}",
            json={"frequency": "weekly", "schedule_day": 31},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_pause_schedule(self, test_client):
        """Pause a recurring schedule."""
        # Create client and schedule
        client_response = await test_client.post(
            "/api/clients", json={"name": "Test Client"}
        )
        client_id = client_response.json()["id"]

        create_response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "To Pause",
                "frequency": "monthly",
            },
        )
        schedule_id = create_response.json()["id"]

        # Pause it
        response = await test_client.post(f"/api/recurring/{schedule_id}/pause")
        assert response.status_code == 200

        data = response.json()
        assert data["is_active"] == 0

    @pytest.mark.asyncio
    async def test_resume_schedule(self, test_client):
        """Resume a paused schedule."""
        # Create client and schedule
        client_response = await test_client.post(
            "/api/clients", json={"name": "Test Client"}
        )
        client_id = client_response.json()["id"]

        create_response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "To Resume",
                "frequency": "monthly",
            },
        )
        schedule_id = create_response.json()["id"]

        # Pause then resume
        await test_client.post(f"/api/recurring/{schedule_id}/pause")
        response = await test_client.post(f"/api/recurring/{schedule_id}/resume")
        assert response.status_code == 200

        data = response.json()
        assert data["is_active"] == 1

    @pytest.mark.asyncio
    async def test_trigger_schedule(self, test_client):
        """Manually trigger a recurring schedule."""
        # Create client and schedule
        client_response = await test_client.post(
            "/api/clients", json={"name": "Trigger Client"}
        )
        client_id = client_response.json()["id"]

        create_response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "To Trigger",
                "frequency": "monthly",
                "schedule_day": 1,
                "line_items": [
                    {"description": "Service", "quantity": 1, "unit_type": "qty", "unit_price": "100.00"}
                ],
            },
        )
        schedule_id = create_response.json()["id"]

        # Trigger it
        response = await test_client.post(f"/api/recurring/{schedule_id}/trigger")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "invoice_id" in data
        assert "invoice_number" in data

    @pytest.mark.asyncio
    async def test_delete_schedule(self, test_client):
        """Delete a recurring schedule."""
        # Create client and schedule
        client_response = await test_client.post(
            "/api/clients", json={"name": "Delete Client"}
        )
        client_id = client_response.json()["id"]

        create_response = await test_client.post(
            "/api/recurring",
            json={
                "client_id": client_id,
                "name": "To Delete",
                "frequency": "monthly",
            },
        )
        schedule_id = create_response.json()["id"]

        # Delete it
        response = await test_client.delete(f"/api/recurring/{schedule_id}")
        assert response.status_code == 204

        # Verify deleted
        get_response = await test_client.get(f"/api/recurring/{schedule_id}")
        assert get_response.status_code == 404



