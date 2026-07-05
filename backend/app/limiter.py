import ipaddress

from fastapi import Request
from slowapi import Limiter


def _is_trusted_proxy(host: str | None) -> bool:
    """Only a loopback/private-network peer (i.e. the local Caddy reverse proxy)
    is allowed to set the forwarded-IP headers we key rate limits on."""
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def _real_ip(request: Request) -> str:
    """
    Return the true client IP for rate-limit keying.

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
