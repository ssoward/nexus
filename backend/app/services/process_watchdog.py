"""
Periodically checks whether PTY processes are still alive and updates
session status in SQLite. Also handles token cleanup and idle timeouts.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from app.config import get_settings
from app.services import pty_service
from app.models.session import SessionStatus

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5        # seconds between process liveness checks
CLEANUP_INTERVAL = 12    # poll ticks between token/revocation cleanup (~60 s)


async def sweep_dead_processes(db) -> None:
    """Mark sessions STOPPED whose PTY process has exited, and reap the fd."""
    statuses = pty_service.check_all()
    for session_id, alive in statuses.items():
        if not alive:
            logger.info("Session %s process exited — marking stopped", session_id[:8])
            await db.execute(
                "UPDATE sessions SET status = ? WHERE id = ? AND status = ?",
                (SessionStatus.STOPPED.value, session_id, SessionStatus.RUNNING.value),
            )
            pty_service.kill(session_id)


async def sweep_idle_sessions(db, idle_timeout_seconds: int) -> None:
    """Stop sessions idle longer than the configured timeout (0 = disabled)."""
    if idle_timeout_seconds <= 0:
        return
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=idle_timeout_seconds)
    ).isoformat()
    idle_rows = await db.fetchall(
        "SELECT id FROM sessions WHERE status = ? AND last_active_at < ?",
        (SessionStatus.RUNNING.value, cutoff),
    )
    for row in idle_rows:
        sid = row["id"]
        logger.info("Session %s idle timeout — stopping", sid[:8])
        pty_service.kill(sid)
        await db.execute(
            "UPDATE sessions SET status = ? WHERE id = ?",
            (SessionStatus.STOPPED.value, sid),
        )


async def cleanup_expired_tokens(db) -> None:
    """Purge expired WS/revoked/OTP/recovery rows. All cutoffs are ISO-8601 to
    match the stored `T`-separated expires_at (SQLite's space-separated
    datetime('now', ...) never compared equal — that bug is fixed here)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    # Expire one-time WS tokens (HIGH-4)
    await db.execute("DELETE FROM ws_tokens WHERE expires_at < ?", (now_iso,))
    # Expire revoked token records once the JWT TTL has passed (HIGH-3)
    await db.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (now_iso,))
    # Expired email OTP codes and recovery tokens
    from app.services.otp_service import cleanup_expired_otps
    await cleanup_expired_otps()
    recovery_cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    await db.execute(
        "DELETE FROM account_recovery_tokens WHERE expires_at < ?",
        (recovery_cutoff,),
    )


async def watch_processes(db) -> None:
    """Long-running background task."""
    cleanup_tick = 0

    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL)
            cleanup_tick += 1

            s = get_settings()
            await sweep_dead_processes(db)
            await sweep_idle_sessions(db, s.session_idle_timeout_seconds)

            if cleanup_tick >= CLEANUP_INTERVAL:
                cleanup_tick = 0
                await cleanup_expired_tokens(db)

        except asyncio.CancelledError:
            logger.info("Process watchdog cancelled")
            return
        except Exception as e:
            logger.warning("Process watchdog error: %s", e)
