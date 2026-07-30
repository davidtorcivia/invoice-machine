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
        """Cloudflare-proxied requests may reach Insights, without weakening script-src.

        Insights loads from its own origin with a src attribute, so allowing the
        host is sufficient. It previously also granted 'unsafe-inline', which was
        both unnecessary for Insights and the only reason the SPA booted at all
        (see TestSpaContentSecurityPolicy in tests/test_security.py).
        """
        response = await test_client.get("/health", headers={"cf-ray": "test-ray-id"})
        assert response.status_code == 200

        csp = response.headers.get("content-security-policy", "")
        assert "https://static.cloudflareinsights.com" in csp
        assert "connect-src 'self' https://cloudflareinsights.com" in csp

        script_src = next(
            (d.strip() for d in csp.split(";") if d.strip().startswith("script-src ")), ""
        )
        assert "'unsafe-inline'" not in script_src

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
        assert init_response.json()["result"]["serverInfo"]["name"] == "invoice-machine"

        assert list_response.status_code == 200
        tool_names = {t["name"] for t in list_response.json()["result"]["tools"]}
        assert "get_business_profile" in tool_names


class TestMcpModernProtocol:
    """Tests for MCP spec 2026-07-28: the stateless, handshake-free protocol.

    Modern clients send no initialize; every request carries its own protocol
    version and client identity in params._meta. These run against the same
    /mcp endpoint that TestMcpStreamableHttp exercises with the old handshake,
    which is the point - one endpoint serves both eras.
    """

    PROTOCOL_VERSION = "2026-07-28"
    META_VERSION = "io.modelcontextprotocol/protocolVersion"
    META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"

    HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    @classmethod
    def _envelope(cls, method: str, request_id: int = 1, version: str | None = None, **params):
        """Build a self-describing request in the 2026-07-28 format."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": {
                **params,
                "_meta": {
                    cls.META_VERSION: version or cls.PROTOCOL_VERSION,
                    "io.modelcontextprotocol/clientCapabilities": {},
                    cls.META_CLIENT_INFO: {"name": "test", "version": "0"},
                },
            },
        }

    async def _post(self, mcp_key, method, **kwargs):
        """POST one modern request, including the now-required routing header."""
        from invoice_machine.api.mcp import streamable_http_lifespan

        version = kwargs.get("version") or self.PROTOCOL_VERSION
        headers = {
            **self.HEADERS,
            "Authorization": f"Bearer {mcp_key}",
            # The transport routes on this header to pick the protocol era: any
            # value outside the handshake versions selects the 2026-07-28 path.
            "MCP-Protocol-Version": version,
            # SEP-2243: proxies route and meter on this without parsing the body.
            "Mcp-Method": kwargs.pop("header_method", method),
        }
        body = self._envelope(method, **kwargs)

        mcp_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        try:
            async with streamable_http_lifespan():
                return await mcp_client.post("/mcp", headers=headers, json=body)
        finally:
            await mcp_client.aclose()

    @staticmethod
    async def _key(test_client):
        response = await test_client.post("/api/profile/mcp-key")
        return response.json()["mcp_api_key"]

    @pytest.mark.asyncio
    async def test_tools_list_without_handshake(self, test_client):
        """A modern client gets tools straight away - no initialize first."""
        response = await self._post(await self._key(test_client), "tools/list")

        assert response.status_code == 200
        result = response.json()["result"]
        tool_names = {t["name"] for t in result["tools"]}
        assert "get_business_profile" in tool_names

    @pytest.mark.asyncio
    async def test_results_carry_result_type_and_server_identity(self, test_client):
        """Every 2026-07-28 result is tagged complete and identifies the server."""
        response = await self._post(await self._key(test_client), "tools/list")
        result = response.json()["result"]

        # resultType distinguishes a finished result from an MRTR interim one.
        assert result["resultType"] == "complete"
        server_info = result["_meta"]["io.modelcontextprotocol/serverInfo"]
        assert server_info["name"] == "invoice-machine"

    @pytest.mark.asyncio
    async def test_tools_list_advertises_cache_hints(self, test_client):
        """SEP-2549: our configured TTL reaches the wire, so clients can cache."""
        response = await self._post(await self._key(test_client), "tools/list")
        result = response.json()["result"]

        assert result["ttlMs"] == 300_000
        assert result["cacheScope"] == "private"

    @pytest.mark.asyncio
    async def test_server_discover_advertises_versions(self, test_client):
        """server/discover replaces initialize for up-front capability discovery."""
        response = await self._post(await self._key(test_client), "server/discover")

        assert response.status_code == 200
        result = response.json()["result"]
        assert self.PROTOCOL_VERSION in result["supportedVersions"]
        assert result["capabilities"]["tools"] is not None
        server_info = result["_meta"]["io.modelcontextprotocol/serverInfo"]
        assert server_info["name"] == "invoice-machine"

    @pytest.mark.asyncio
    async def test_unsupported_protocol_version_is_rejected(self, test_client):
        """A version we don't speak fails loudly rather than being guessed at."""
        response = await self._post(
            await self._key(test_client), "tools/list", version="1999-01-01"
        )

        # -32022 is UnsupportedProtocolVersion under the new error-code policy.
        assert response.json()["error"]["code"] == -32022

    @pytest.mark.asyncio
    async def test_mismatched_routing_header_is_rejected(self, test_client):
        """A Mcp-Method header disagreeing with the body is refused, not trusted.

        Infrastructure routes on the header, so letting it diverge from the
        JSON body would let a caller be metered as one method and run another.
        """
        response = await self._post(
            await self._key(test_client), "tools/list", header_method="tools/call"
        )

        # -32020 is HeaderMismatch.
        assert response.json()["error"]["code"] == -32020


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
