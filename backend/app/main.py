import asyncio
import logging
import os
import subprocess
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.crypto import init_crypto
from app.database import db
from app.limiter import limiter
from app.logging_config import configure_logging
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import auth, sessions, ws, orchestration, health, metrics as metrics_router, workspaces, pages
from app.services import pty_service, pty_broadcaster
from app.services.process_watchdog import watch_processes
from app.services.session_service import reset_running_sessions_on_startup

# Initial logging until settings are loaded
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

_watchdog_task: asyncio.Task | None = None
_tls_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _watchdog_task

    s = get_settings()
    configure_logging(s.log_level, getattr(s, 'log_format', 'text'))
    init_crypto(s.app_secret, s.crypto_salt)

    # Ensure the database directory exists with restrictive permissions
    db_dir = os.path.dirname(s.db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
        os.chmod(db_dir, 0o700)

    # Run migrations (use sys.executable-relative alembic so we work inside venv or Docker)
    logger.info("Running database migrations...")
    alembic_bin = os.path.join(os.path.dirname(sys.executable), "alembic")
    if not os.path.exists(alembic_bin):
        alembic_bin = "alembic"  # fallback to PATH
    result = subprocess.run(
        [alembic_bin, "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env={**os.environ, "DB_PATH": s.db_path},
    )
    if result.returncode != 0:
        logger.error("Migration failed: %s", result.stderr)
        raise RuntimeError("Database migration failed")
    logger.info("Migrations complete")

    db._init(s.db_path)
    await db.connect()
    logger.info("Database connected: %s", s.db_path)

    recovery_mode = s.recovery_enabled
    if recovery_mode:
        from app.services.recovery import load_recovery
        if load_recovery(s.recovery_ttl_hours) is not None:
            logger.info("Recovery file found — marking sessions as RECOVERY_PENDING")
        else:
            recovery_mode = False
    await reset_running_sessions_on_startup(recovery_mode=recovery_mode)

    _watchdog_task = asyncio.create_task(watch_processes(db))
    logger.info("Process watchdog started")

    health.set_startup_time(time.monotonic())

    if s.tls_auto_renew and s.tls_domain:
        from app.services.tls_renewal import tls_renewal_loop
        _tls_task = asyncio.create_task(tls_renewal_loop(s.tls_domain, s.tls_cert_dir))
        logger.info("TLS auto-renewal started for %s", s.tls_domain)

    yield

    # ── Graceful shutdown ────────────────────────────────────────────────
    logger.info("Shutdown initiated")

    # 1. Notify all WS subscribers that sessions are ending
    pty_broadcaster.broadcast_shutdown()

    # 2. Close all WebSocket connections
    for ws_conn in ws.get_active_websockets():
        try:
            await ws_conn.close(code=1001, reason="Server shutting down")
        except Exception:
            pass

    # 3. Cancel watchdog
    if _watchdog_task and not _watchdog_task.done():
        _watchdog_task.cancel()
        try:
            await _watchdog_task
        except asyncio.CancelledError:
            pass

    # 4. Cancel TLS renewal
    if _tls_task and not _tls_task.done():
        _tls_task.cancel()
        try:
            await _tls_task
        except asyncio.CancelledError:
            pass

    # 5. Save recovery data before killing PTYs
    if s.recovery_enabled:
        from app.services.recovery import save_recovery
        save_recovery()

    # 6. Kill all PTY processes (SIGTERM, wait 5s, SIGKILL)
    pty_service.kill_all(timeout=5.0)

    # 7. Close database
    await db.close()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Nexus Terminal Gateway",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

# Rate limiter state must be set before adding middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(health.router)
app.include_router(metrics_router.router)
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(ws.router)
app.include_router(orchestration.router)
app.include_router(workspaces.router)
app.include_router(pages.router)

static_dir = os.getenv("STATIC_DIR", "")
if static_dir and os.path.isdir(static_dir):
    # Serve static assets (JS, CSS, images) from the frontend build directory
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="static-assets")

    # SPA fallback: serve index.html for all non-API, non-asset routes
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        return FileResponse(os.path.join(static_dir, "index.html"))
