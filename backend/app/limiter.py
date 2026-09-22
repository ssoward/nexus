import ipaddress

from fastapi import Request
from slowapi import Limiter


# Where the Caddy container can legitimately connect from: loopback (macOS
# Docker Desktop / colima forward host.docker.internal via 127.0.0.1) or the
# RFC 1918 bridge ranges (Linux `host-gateway`). Deliberately NOT Python's
# broader `is_private`, which also covers 100.64.0.0/10 — the Tailscale CGNAT
# range — and would let any tailnet peer that reached the backend directly
# spoof X-Real-IP.
_TRUSTED_PROXY_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


def _is_trusted_proxy(host: str | None) -> bool:
    """Only the local Caddy reverse proxy is allowed to set the forwarded-IP
    headers we key rate limits and audit rows on."""
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in net for net in _TRUSTED_PROXY_NETS)


def _real_ip(request) -> str:
    """
    Return the true client IP for rate-limit keying and audit rows.

    Accepts a Request or a WebSocket (both expose .client and .headers).

    Caddy overwrites X-Real-IP / X-Forwarded-For with the real peer and connects
    from a loopback/private address, so we honor those headers ONLY when the direct
    peer is a trusted proxy. If a request reaches the backend directly (port exposed,
    dev mode), the client-supplied headers are ignored and we key on the peer IP —
    otherwise an attacker could rotate X-Real-IP to defeat brute-force limits.
    """
    peer = request.client.host if request.client else None
    if _is_trusted_proxy(peer):
        real = request.headers.get("X-Real-IP")
        if real:
            return real.strip()
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return peer or "127.0.0.1"


limiter = Limiter(key_func=_real_ip)
