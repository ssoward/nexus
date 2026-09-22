"""Cross-site request defence for state-changing requests and WebSocket upgrades.

SameSite=Strict on the session cookie already stops browsers attaching it to
cross-site requests, but this app lets a single JSON POST type into a host
shell, so it gets a second, independent layer:

* `Sec-Fetch-Site: cross-site` is rejected outright (every modern browser sets
  this header; a non-browser client never sends it and is unaffected).
* If an `Origin` header is present it must be one of ours: the configured
  WebAuthn origin (or https://rp_id), or the request's own Host over http(s),
  which a cross-site page cannot influence. Requests without an Origin header
  (curl, wctl.py, same-origin GET navigations) are left alone — the cookie is
  still required for anything that matters.

The same `origin_rejection()` check runs on the WebSocket handshake so a page
on another origin cannot open a terminal socket even if it somehow obtained a
WS token (cross-site WebSocket hijacking).
"""
from typing import Mapping
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "[::1]"})


def _allowed_origins(host_header: str | None) -> set[str]:
    s = get_settings()
    allowed = {(s.webauthn_origin or f"https://{s.rp_id}").rstrip("/").lower()}
    if host_header:
        h = host_header.strip().lower()
        allowed.add(f"https://{h}")
        allowed.add(f"http://{h}")
    return allowed


def origin_rejection(headers: Mapping[str, str]) -> str | None:
    """Return a human-readable reason to refuse the request, or None to allow it."""
    fetch_site = (headers.get("sec-fetch-site") or "").strip().lower()
    if fetch_site == "cross-site":
        return "Cross-site requests are not allowed"

    origin = (headers.get("origin") or "").strip()
    if not origin or origin.lower() == "null":
        return None if origin == "" else "Requests from an opaque origin are not allowed"

    normalized = origin.rstrip("/").lower()
    if normalized in _allowed_origins(headers.get("host")):
        return None

    # Local development (rp_id=localhost): the Vite dev server on :5173 proxies
    # to :8000 but the browser still reports its own origin.
    if get_settings().rp_id == "localhost":
        parsed = urlsplit(normalized)
        if parsed.hostname in _LOOPBACK_HOSTS or (parsed.hostname or "") == "localhost":
            return None

    return "Origin not allowed"


class OriginCheckMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in _SAFE_METHODS:
            reason = origin_rejection(request.headers)
            if reason:
                return JSONResponse(status_code=403, content={"detail": reason})
        return await call_next(request)
