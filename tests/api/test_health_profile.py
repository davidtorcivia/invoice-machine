
import pytest
from httpx import ASGITransport, AsyncClient

from invoice_machine.main import app


class TestHealthEndpoint:
    """Tests for health check."""

    @pytest.mark.asyncio
    async def test_health_check(self, test_client):
        """Health check returns 200."""
        response = await test_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    @pytest.mark.asyncio
    async def test_cloudflare_csp_allows_insights_scripts(self, test_client):
        """Cloudflare-proxied requests get compatible CSP for Rocket Loader/Insights."""
        response = await test_client.get("/health", headers={"cf-ray": "test-ray-id"})
        assert response.status_code == 200

        csp = response.headers.get("content-security-policy", "")
        assert "script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com" in csp
        assert "connect-src 'self' https://cloudflareinsights.com" in csp

    @pytest.mark.asyncio
    async def test_cors_preflight_allows_csrf_header(self, test_client):
        """CORS preflight allows the CSRF header required for unsafe methods."""
        response = await test_client.options(
            "/api/clients",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-CSRF-Token, Content-Type",
            },
        )
        assert response.status_code == 200
        allow_headers = response.headers.get("access-control-allow-headers", "").lower()
        assert "x-csrf-token" in allow_headers

    @pytest.mark.asyncio
    async def test_mcp_sse_post_returns_405_instead_of_crashing(self, test_client):
        """Mounted MCP routes should not crash in top-level middleware."""
        key_response = await test_client.post("/api/profile/mcp-key")
        mcp_key = key_response.json()["mcp_api_key"]

        mcp_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        try:
            response = await mcp_client.post(
                "/mcp/sse",
                headers={"Authorization": f"Bearer {mcp_key}"},
            )
        finally:
            await mcp_client.aclose()

        assert response.status_code == 405


class TestMcpStreamableHttp:
    """Tests for the Streamable HTTP MCP transport at /mcp."""

    HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    @staticmethod
    def _rpc(method: str, request_id: int = 1, **params):
        return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}

    @pytest.mark.asyncio
    async def test_requires_bearer_auth(self, test_client):
        """POST /mcp without a valid key is rejected before reaching the transport."""
        from invoice_machine.api.mcp import streamable_http_lifespan

        await test_client.post("/api/profile/mcp-key")  # key configured, but not sent

        mcp_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        try:
            async with streamable_http_lifespan():
                response = await mcp_client.post(
                    "/mcp", headers=self.HEADERS, json=self._rpc("initialize")
                )
        finally:
            await mcp_client.aclose()

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_503_when_session_manager_not_running(self, test_client):
        """Outside the app lifespan the endpoint fails closed instead of crashing."""
        key_response = await test_client.post("/api/profile/mcp-key")
        mcp_key = key_response.json()["mcp_api_key"]

        mcp_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        try:
            response = await mcp_client.post(
                "/mcp",
                headers={**self.HEADERS, "Authorization": f"Bearer {mcp_key}"},
                json=self._rpc("initialize"),
            )
        finally:
            await mcp_client.aclose()

        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_stateless_tool_calls_work_without_session(self, test_client):
        """Each request stands alone: initialize and a bare tools/list both succeed.

        This is the property that fixes the Cloudflare drop bug — no server-side
        session means nothing to lose when a connection dies.
        """
        from invoice_machine.api.mcp import streamable_http_lifespan

        key_response = await test_client.post("/api/profile/mcp-key")
        mcp_key = key_response.json()["mcp_api_key"]
        headers = {**self.HEADERS, "Authorization": f"Bearer {mcp_key}"}

        mcp_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        try:
            async with streamable_http_lifespan():
                init_response = await mcp_client.post(
                    "/mcp",
                    headers=headers,
                    json=self._rpc(
                        "initialize",
                        protocolVersion="2025-03-26",
                        capabilities={},
                        clientInfo={"name": "test", "version": "0"},
                    ),
                )
                # No session header carried over: stateless mode must still serve this.
                list_response = await mcp_client.post(
                    "/mcp", headers=headers, json=self._rpc("tools/list", request_id=2)
                )
        finally:
            await mcp_client.aclose()

        assert init_response.status_code == 200
        assert (
            init_response.json()["result"]["serverInfo"]["name"] == "invoice-machine"
        )

        assert list_response.status_code == 200
        tool_names = {t["name"] for t in list_response.json()["result"]["tools"]}
        assert "get_business_profile" in tool_names


class TestProfileEndpoints:
    """Tests for business profile endpoints."""

    @pytest.mark.asyncio
    async def test_get_profile(self, test_client):
        """Get business profile."""
        response = await test_client.get("/api/profile")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Test Business"
        assert data["business_name"] == "Test LLC"
        assert data["mcp_api_key_configured"] is False
        assert data["bot_api_key_configured"] is False

    @pytest.mark.asyncio
    async def test_update_profile(self, test_client):
        """Update business profile."""
        response = await test_client.put(
            "/api/profile", json={"name": "Updated Name", "phone": "555-1234"}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["phone"] == "555-1234"

    @pytest.mark.asyncio
    async def test_partial_update(self, test_client):
        """Partial update only changes provided fields."""
        response = await test_client.put("/api/profile", json={"phone": "555-9999"})
        assert response.status_code == 200

        # Name should be unchanged
        data = response.json()
        assert data["name"] == "Test Business"
        assert data["phone"] == "555-9999"

    @pytest.mark.asyncio
    async def test_restore_guard_rejects_requests_during_backup_restore(self, test_client):
        """App returns 503 for new requests while restore mode is active."""
        app.state.restore_in_progress = True
        try:
            response = await test_client.get("/api/profile")
        finally:
            app.state.restore_in_progress = False

        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_generate_bot_key(self, test_client):
        """Generate bot API key and mark profile as configured."""
        response = await test_client.post("/api/profile/bot-key")
        assert response.status_code == 200
        data = response.json()
        assert "bot_api_key" in data
        assert isinstance(data["bot_api_key"], str)
        assert len(data["bot_api_key"]) >= 32

        profile_response = await test_client.get("/api/profile")
        profile_data = profile_response.json()
        assert profile_data["bot_api_key_configured"] is True

    @pytest.mark.asyncio
    async def test_delete_bot_key(self, test_client):
        """Delete bot API key and mark profile as unconfigured."""
        await test_client.post("/api/profile/bot-key")

        response = await test_client.delete("/api/profile/bot-key")
        assert response.status_code == 200
        assert response.json()["success"] is True

        profile_response = await test_client.get("/api/profile")
        profile_data = profile_response.json()
        assert profile_data["bot_api_key_configured"] is False


class TestBotApiKeyAuth:
    """Tests for bearer-token auth using dedicated bot API key."""

    @pytest.mark.asyncio
    async def test_bot_key_allows_conventional_api_calls(self, test_client):
        """Bot key can authenticate GET and unsafe methods without CSRF."""
        generate_response = await test_client.post("/api/profile/bot-key")
        bot_key = generate_response.json()["bot_api_key"]

        bot_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        headers = {"Authorization": f"Bearer {bot_key}"}
        try:
            profile_response = await bot_client.get("/api/profile", headers=headers)
            assert profile_response.status_code == 200

            create_response = await bot_client.post(
                "/api/clients",
                headers=headers,
                json={"name": "Bot Client", "email": "bot@example.com"},
            )
            assert create_response.status_code == 201
        finally:
            await bot_client.aclose()

    @pytest.mark.asyncio
    async def test_invalid_bot_key_is_rejected(self, test_client):
        """Invalid bearer token does not bypass authentication."""
        bot_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        try:
            response = await bot_client.get(
                "/api/profile",
                headers={"Authorization": "Bearer invalid-key"},
            )
            assert response.status_code == 401
        finally:
            await bot_client.aclose()



class TestTaxSettingsEndpoints:
    """Tests for tax settings in profile API."""

    @pytest.mark.asyncio
    async def test_get_profile_includes_tax_settings(self, test_client):
        """Profile response includes tax settings."""
        response = await test_client.get("/api/profile")
        assert response.status_code == 200

        data = response.json()
        assert "default_tax_enabled" in data
        assert "default_tax_rate" in data
        assert "default_tax_name" in data

    @pytest.mark.asyncio
    async def test_update_tax_settings(self, test_client):
        """Update tax settings via profile."""
        response = await test_client.put(
            "/api/profile",
            json={
                "default_tax_enabled": True,
                "default_tax_rate": "8.25",
                "default_tax_name": "Sales Tax",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["default_tax_enabled"] is True
        assert data["default_tax_rate"] == "8.25"
        assert data["default_tax_name"] == "Sales Tax"

