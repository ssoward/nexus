"""Cross-site request / WebSocket-origin defence (M3) and forwarded-IP audit rows (L1)."""
import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.limiter import _real_ip
from app.middleware.origin_check import origin_rejection


class TestOriginRejection:
    def test_no_headers_allowed(self):
        assert origin_rejection({}) is None

    def test_cross_site_fetch_metadata_rejected(self):
        assert origin_rejection({"sec-fetch-site": "cross-site", "origin": "https://evil.example"}) is not None

    def test_same_origin_fetch_metadata_allowed(self):
        assert origin_rejection({"sec-fetch-site": "same-origin"}) is None

    def test_configured_origin_allowed(self, monkeypatch):
        s = get_settings()
        monkeypatch.setattr(s, "webauthn_origin", "https://nexus.example.ts.net")
        assert origin_rejection({"origin": "https://nexus.example.ts.net"}) is None
        assert origin_rejection({"origin": "https://NEXUS.example.ts.net/"}) is None

    def test_origin_matching_host_header_allowed(self, monkeypatch):
        s = get_settings()
        monkeypatch.setattr(s, "webauthn_origin", "https://primary.example.ts.net")
        # Secondary machine serving on its own name: Origin == Host is fine.
        assert origin_rejection({"origin": "https://m5.example.ts.net", "host": "m5.example.ts.net"}) is None

    def test_foreign_origin_rejected(self, monkeypatch):
        s = get_settings()
        monkeypatch.setattr(s, "webauthn_origin", "https://nexus.example.ts.net")
        assert origin_rejection({"origin": "https://evil.example", "host": "nexus.example.ts.net"}) is not None

    def test_null_origin_rejected(self):
        assert origin_rejection({"origin": "null"}) is not None

    def test_localhost_dev_origins_allowed_when_rp_is_localhost(self, monkeypatch):
        s = get_settings()
        monkeypatch.setattr(s, "rp_id", "localhost")
        monkeypatch.setattr(s, "webauthn_origin", "http://localhost:8000")
        assert origin_rejection({"origin": "http://localhost:5173", "host": "localhost:8000"}) is None
        assert origin_rejection({"origin": "https://evil.example", "host": "localhost:8000"}) is not None


class TestMiddleware:
    async def test_cross_site_post_is_refused_before_auth(self, client: AsyncClient, setup_db, test_user):
        r = await client.post(
            "/api/auth/login",
            data={"username": test_user["username"], "password": test_user["password"]},
            headers={"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"},
        )
        assert r.status_code == 403
        assert "cross-site" in r.json()["detail"].lower()

    async def test_foreign_origin_post_refused(self, client: AsyncClient, setup_db, test_user):
        r = await client.post(
            "/api/auth/login",
            data={"username": test_user["username"], "password": test_user["password"]},
            headers={"Origin": "https://evil.example"},
        )
        assert r.status_code == 403

    async def test_same_origin_post_passes_through(self, client: AsyncClient, setup_db, test_user):
        # Origin equal to the request Host is what a real browser sends same-origin.
        r = await client.post(
            "/api/auth/login",
            data={"username": test_user["username"], "password": test_user["password"]},
            headers={"Origin": "http://test", "Sec-Fetch-Site": "same-origin"},
        )
        assert r.status_code == 200  # reaches the router (needs_mfa_setup)

    async def test_get_is_never_blocked(self, client: AsyncClient, setup_db):
        r = await client.get("/api/auth/me", headers={"Origin": "https://evil.example"})
        assert r.status_code == 401  # auth failure, not the origin check

    async def test_orchestration_input_refused_cross_site(self, auth_client):
        ac, _ = auth_client
        r = await ac.post(
            "/api/orchestration/sessions/00000000-0000-0000-0000-000000000000/input",
            json={"data": "rm -rf /\n"},
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        assert r.status_code == 403


class TestRealIp:
    class _Req:
        def __init__(self, peer, headers):
            self.client = type("C", (), {"host": peer})() if peer else None
            self.headers = headers

    def test_forwarded_header_honoured_from_loopback_proxy(self):
        req = self._Req("127.0.0.1", {"X-Real-IP": "100.64.0.9"})
        assert _real_ip(req) == "100.64.0.9"

    def test_forwarded_header_ignored_from_public_peer(self):
        req = self._Req("8.8.8.8", {"X-Real-IP": "100.64.0.9"})
        assert _real_ip(req) == "8.8.8.8"

    def test_tailnet_peer_is_not_a_trusted_proxy(self):
        """100.64.0.0/10 is Python-'private' but it is the Tailscale range: a peer
        that reaches the backend directly must not be able to spoof X-Real-IP."""
        req = self._Req("100.101.102.103", {"X-Real-IP": "1.2.3.4"})
        assert _real_ip(req) == "100.101.102.103"

    def test_works_for_websocket_like_objects(self):
        # WebSocket exposes the same .client/.headers shape.
        req = self._Req("127.0.0.1", {"X-Forwarded-For": "100.64.0.7, 10.0.0.1"})
        assert _real_ip(req) == "100.64.0.7"

    async def test_audit_rows_record_forwarded_ip(self, client: AsyncClient, setup_db, test_user):
        """Behind Caddy the peer is loopback; the audit row must carry the tailnet IP."""
        # httpx's ASGI transport reports the peer as 127.0.0.1, i.e. a trusted proxy.
        await client.post(
            "/api/auth/login",
            data={"username": test_user["username"], "password": "WrongPassword9!"},
            headers={"X-Real-IP": "100.64.0.42"},
        )
        row = await setup_db.fetchone(
            "SELECT ip_address FROM audit_log WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (test_user["id"],),
        )
        assert row["ip_address"] == "100.64.0.42"
