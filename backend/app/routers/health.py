import ipaddress
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.database import db
from app.limiter import _real_ip
from app.services import pty_service

router = APIRouter(tags=["health"])


def _is_local_caller(request: Request) -> bool:
    """True when the *resolved* client (behind Caddy: the forwarded IP) is loopback,
    i.e. start.sh / launchd probes on the box itself rather than a tailnet or LAN peer."""
    try:
        return ipaddress.ip_address(_real_ip(request)).is_loopback
    except ValueError:
        return False

_startup_time: float = 0.0


def set_startup_time(t: float) -> None:
    global _startup_time
    _startup_time = t


@router.get("/api/health")
async def health_check(request: Request):
    """Liveness probe. Unauthenticated, so remote callers only learn up/degraded;
    version, uptime and per-component detail are reserved for loopback callers."""
    detailed = _is_local_caller(request)
    checks = {}
    status = "healthy"

    # Database
    try:
        row = await db.fetchone("SELECT 1 AS ok")
        checks["database"] = "ok" if row else "error"
    except Exception:
        checks["database"] = "error"
        status = "degraded"

    # Watchdog
    from app.main import _watchdog_task
    if _watchdog_task is None or _watchdog_task.done():
        checks["watchdog"] = "stale"
        status = "degraded"
    else:
        checks["watchdog"] = "ok"

    # PTY service
    try:
        pty_service.check_all()
        checks["pty_service"] = "ok"
    except Exception:
        checks["pty_service"] = "error"
        status = "degraded"

    if not detailed:
        return {"status": status}
    return {
        "status": status,
        "checks": checks,
        "uptime_seconds": round(time.monotonic() - _startup_time, 1),
        "version": "1.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
