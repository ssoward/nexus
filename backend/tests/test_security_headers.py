"""Tests for SecurityHeadersMiddleware (CSP, HSTS, anti-clickjacking)."""
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.middleware.security_headers import SecurityHeadersMiddleware


def _app():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


@pytest.fixture
async def sec_client():
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as ac:
        yield ac


async def test_core_security_headers_present(sec_client):
    r = await sec_client.get("/ping")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "microphone=(self)" in r.headers["Permissions-Policy"]


async def test_csp_allows_https_frames_but_denies_framing(sec_client):
    """frame-src https: lets the Pages feature embed external iframes;
    frame-ancestors 'none' still blocks Nexus itself from being framed."""
    r = await sec_client.get("/ping")
    csp = r.headers["Content-Security-Policy"]
    assert "frame-src https:" in csp
    assert "frame-ancestors 'none'" in csp
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp


async def test_hsts_only_on_https(sec_client):
    # Plain http request → no HSTS
    r = await sec_client.get("/ping")
    assert "Strict-Transport-Security" not in r.headers
    # Forwarded-proto https → HSTS present with preload
    r = await sec_client.get("/ping", headers={"x-forwarded-proto": "https"})
    assert "preload" in r.headers["Strict-Transport-Security"]
