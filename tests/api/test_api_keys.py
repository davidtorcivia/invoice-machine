"""Tests for labeled, individually revocable API keys."""

import pytest
from httpx import ASGITransport, AsyncClient

from invoice_machine.main import app


async def create_key(test_client, kind: str, label: str = "Laptop"):
    response = await test_client.post("/api/api-keys", json={"kind": kind, "label": label})
    assert response.status_code == 201, response.text
    return response.json()


def bearer_client(key: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {key}"},
    )


class TestApiKeyManagement:
    """Create, list, rename, rotate, revoke."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["mcp", "bot"])
    async def test_create_returns_prefixed_key_once(self, test_client, kind):
        data = await create_key(test_client, kind, "Desk machine")

        assert data["key"].startswith(f"im_{kind}_")
        assert data["prefix"] == data["key"][:12]
        assert data["kind"] == kind
        assert data["label"] == "Desk machine"
        assert data["last_used_at"] is None
        assert "only shown once" in data["warning"]

        listed = (await test_client.get("/api/api-keys")).json()
        assert [row["id"] for row in listed] == [data["id"]]
        assert "key" not in listed[0]

    @pytest.mark.asyncio
    async def test_list_returns_every_key(self, test_client):
        await create_key(test_client, "mcp", "One")
        await create_key(test_client, "bot", "Two")

        listed = (await test_client.get("/api/api-keys")).json()
        assert {(row["kind"], row["label"]) for row in listed} == {("mcp", "One"), ("bot", "Two")}

    @pytest.mark.asyncio
    async def test_rename_keeps_the_secret(self, test_client):
        created = await create_key(test_client, "bot", "Old name")

        response = await test_client.patch(
            f"/api/api-keys/{created['id']}", json={"label": "New name"}
        )
        assert response.status_code == 200
        assert response.json()["label"] == "New name"

        async with bearer_client(created["key"]) as client:
            assert (await client.get("/api/profile")).status_code == 200

    @pytest.mark.asyncio
    async def test_rotate_replaces_the_secret_in_place(self, test_client):
        created = await create_key(test_client, "bot", "Rotating")

        response = await test_client.post(f"/api/api-keys/{created['id']}/rotate")
        assert response.status_code == 200
        rotated = response.json()
        assert rotated["id"] == created["id"]
        assert rotated["label"] == "Rotating"
        assert rotated["key"] != created["key"]
        assert rotated["prefix"] == rotated["key"][:12]

        async with bearer_client(created["key"]) as client:
            assert (await client.get("/api/profile")).status_code == 401
        async with bearer_client(rotated["key"]) as client:
            assert (await client.get("/api/profile")).status_code == 200

    @pytest.mark.asyncio
    async def test_revoke_rejects_the_key(self, test_client):
        created = await create_key(test_client, "bot", "Doomed")

        response = await test_client.delete(f"/api/api-keys/{created['id']}")
        assert response.status_code == 200
        assert response.json() == {"success": True}

        async with bearer_client(created["key"]) as client:
            assert (await client.get("/api/profile")).status_code == 401

    @pytest.mark.asyncio
    async def test_keys_are_revoked_independently(self, test_client):
        first = await create_key(test_client, "bot", "Laptop")
        second = await create_key(test_client, "bot", "CI runner")

        for key in (first, second):
            async with bearer_client(key["key"]) as client:
                assert (await client.get("/api/profile")).status_code == 200

        await test_client.delete(f"/api/api-keys/{first['id']}")

        async with bearer_client(first["key"]) as client:
            assert (await client.get("/api/profile")).status_code == 401
        async with bearer_client(second["key"]) as client:
            assert (await client.get("/api/profile")).status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize("label", ["", "   ", "x" * 101])
    async def test_label_is_validated(self, test_client, label):
        response = await test_client.post("/api/api-keys", json={"kind": "bot", "label": label})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_id_is_404(self, test_client):
        assert (
            await test_client.patch("/api/api-keys/999", json={"label": "x"})
        ).status_code == 404
        assert (await test_client.post("/api/api-keys/999/rotate")).status_code == 404
        assert (await test_client.delete("/api/api-keys/999")).status_code == 404

    @pytest.mark.asyncio
    async def test_last_used_is_recorded(self, test_client):
        created = await create_key(test_client, "bot", "Tracked")

        async with bearer_client(created["key"]) as client:
            assert (await client.get("/api/profile")).status_code == 200

        listed = (await test_client.get("/api/api-keys")).json()
        assert listed[0]["last_used_at"] is not None

    @pytest.mark.asyncio
    async def test_auth_survives_a_failed_last_used_write(self, test_client, monkeypatch):
        """last_used_at is bookkeeping: a failed write must not reject a valid key."""
        created = await create_key(test_client, "bot", "Flaky")

        from sqlalchemy.ext.asyncio import AsyncSession

        async def boom(self):
            raise RuntimeError("commit failed")

        monkeypatch.setattr(AsyncSession, "commit", boom)

        async with bearer_client(created["key"]) as client:
            assert (await client.get("/api/profile")).status_code == 200


class TestApiKeyScopeSeparation:
    """A key of one kind must not authenticate the other kind's surface."""

    @pytest.mark.asyncio
    async def test_bot_key_cannot_manage_api_keys(self, test_client):
        """Key management is web-session-only, so a bot key must not reach it."""
        created = await create_key(test_client, "bot", "Escalating")

        async with bearer_client(created["key"]) as client:
            assert (await client.get("/api/api-keys")).status_code == 401
            response = await client.post(
                "/api/api-keys", json={"kind": "bot", "label": "Minted by a bot"}
            )
            assert response.status_code == 401

    MCP_HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    MCP_BODY = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}

    @pytest.mark.asyncio
    async def test_mcp_key_serves_mcp_but_not_the_rest_api(self, test_client):
        created = await create_key(test_client, "mcp", "Claude Desktop")

        async with bearer_client(created["key"]) as client:
            response = await client.post("/mcp", headers=self.MCP_HEADERS, json=self.MCP_BODY)
            # 503 is the idle transport outside the lifespan: auth already passed.
            assert response.status_code == 503
            assert (await client.get("/api/profile")).status_code == 401

    @pytest.mark.asyncio
    async def test_bot_key_does_not_authenticate_mcp(self, test_client):
        created = await create_key(test_client, "bot", "Script")

        async with bearer_client(created["key"]) as client:
            response = await client.post("/mcp", headers=self.MCP_HEADERS, json=self.MCP_BODY)
            assert response.status_code == 401
