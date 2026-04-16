from fastapi import Request
from slowapi import Limiter


def _real_ip(request: Request) -> str:
    """
    Return the true client IP for rate-limit keying.

    Caddy overwrites X-Real-IP (and X-Forwarded-For) with {remote_host},
    so spoofed headers from the client are stripped before they reach us.
    Falling back to request.client.host handles direct-to-backend access
    (dev mode / health checks) where Caddy is not in the path.
    """
    real = request.headers.get("X-Real-IP")
    if real:
        return real.strip()
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


limiter = Limiter(key_func=_real_ip)
