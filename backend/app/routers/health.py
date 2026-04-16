import time
from datetime import datetime, timezone

from fastapi import APIRouter

from app.database import db
from app.services import pty_service

router = APIRouter(tags=["health"])

_startup_time: float = 0.0


def set_startup_time(t: float) -> None:
    global _startup_time
    _startup_time = t


@router.get("/api/health")
async def health_check():
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

    return {
        "status": status,
        "checks": checks,
        "uptime_seconds": round(time.monotonic() - _startup_time, 1),
        "version": "1.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
