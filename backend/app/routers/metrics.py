from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.services import metrics

router = APIRouter(tags=["metrics"])


@router.get("/api/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    lines = [
        f"# HELP nexus_sessions_created_total Total sessions created",
        f"# TYPE nexus_sessions_created_total counter",
        f"nexus_sessions_created_total {metrics.sessions_created_total.value}",
        f"# HELP nexus_sessions_active Current running sessions",
        f"# TYPE nexus_sessions_active gauge",
        f"nexus_sessions_active {metrics.sessions_active.value}",
        f"# HELP nexus_ws_connections_total Total WebSocket connections",
        f"# TYPE nexus_ws_connections_total counter",
        f"nexus_ws_connections_total {metrics.ws_connections_total.value}",
        f"# HELP nexus_ws_connections_active Current WebSocket connections",
        f"# TYPE nexus_ws_connections_active gauge",
        f"nexus_ws_connections_active {metrics.ws_connections_active.value}",
        f"# HELP nexus_pty_bytes_read_total Total bytes read from PTYs",
        f"# TYPE nexus_pty_bytes_read_total counter",
        f"nexus_pty_bytes_read_total {metrics.pty_bytes_read_total.value}",
        f"# HELP nexus_uptime_seconds Seconds since backend started",
        f"# TYPE nexus_uptime_seconds gauge",
        f"nexus_uptime_seconds {metrics.uptime_seconds():.1f}",
    ]
    return "\n".join(lines) + "\n"
