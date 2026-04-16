import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.database import db
from app.models.session import Session, SessionCreate, SessionStatus
from app.models.audit import AuditAction
from app.services import pty_service, pty_broadcaster, metrics
from app.config import get_settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _write_audit(user_id: int, action: AuditAction, detail: Optional[dict], ip: Optional[str]) -> None:
    await db.execute(
        "INSERT INTO audit_log (user_id, action, detail, ip_address) VALUES (?, ?, ?, ?)",
        (user_id, action.value, json.dumps(detail) if detail else None, ip),
    )


def _row_to_session(row: dict) -> Session:
    return Session(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        image=row["image"],       # reused field — stores the command string
        container_id=row.get("container_id"),  # stores pid as string
        container_name=row["container_name"],
        status=SessionStatus(row["status"]),
        cols=row["cols"],
        rows=row["rows"],
        created_at=row["created_at"],
        last_active_at=row["last_active_at"],
    )


async def list_sessions(user_id: int) -> list[Session]:
    rows = await db.fetchall(
        "SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    return [_row_to_session(r) for r in rows]


async def get_session(session_id: str, user_id: int) -> Optional[Session]:
    row = await db.fetchone(
        "SELECT * FROM sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    )
    return _row_to_session(row) if row else None


async def create_session(user_id: int, req: SessionCreate, ip: Optional[str]) -> Session:
    s = get_settings()

    # `image` field repurposed as the preset/command name
    preset = next((p for p in s.presets if p["name"] == req.image), None)
    if preset is None:
        raise ValueError(f"Unknown preset. Available: {[p['name'] for p in s.presets]}")

    session_id = str(uuid.uuid4())
    now = _now()

    await db.execute(
        """
        INSERT INTO sessions (id, user_id, name, image, container_name, status, cols, rows, created_at, last_active_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, user_id, req.name, req.image, f"session-{session_id[:8]}",
         SessionStatus.PENDING.value, req.cols, req.rows, now, now),
    )

    try:
        cmd = preset["command"]
        pid = pty_service.spawn(session_id, cmd, {}, req.cols, req.rows)
        await pty_broadcaster.ensure_reader(session_id)
        await db.execute(
            "UPDATE sessions SET container_id = ?, status = ? WHERE id = ?",
            (str(pid), SessionStatus.RUNNING.value, session_id),
        )
    except Exception as e:
        await db.execute(
            "UPDATE sessions SET status = ? WHERE id = ?",
            (SessionStatus.ERROR.value, session_id),
        )
        await _write_audit(user_id, AuditAction.SESSION_CREATE, {"error": str(e), "name": req.name}, ip)
        raise

    metrics.sessions_created_total.inc()
    metrics.sessions_active.inc()
    await _write_audit(user_id, AuditAction.SESSION_CREATE, {"name": req.name, "preset": req.image}, ip)
    row = await db.fetchone("SELECT * FROM sessions WHERE id = ?", (session_id,))
    return _row_to_session(row)


async def delete_session(session_id: str, user_id: int, ip: Optional[str]) -> None:
    row = await db.fetchone(
        "SELECT * FROM sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    )
    if not row:
        return

    pty_service.kill(session_id)
    metrics.sessions_active.dec()
    await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    await _write_audit(user_id, AuditAction.SESSION_DELETE, {"name": row["name"]}, ip)


async def update_session_status(session_id: str, status: SessionStatus) -> None:
    await db.execute(
        "UPDATE sessions SET status = ? WHERE id = ?",
        (status.value, session_id),
    )


async def mark_active(session_id: str) -> None:
    await db.execute(
        "UPDATE sessions SET last_active_at = ? WHERE id = ?",
        (_now(), session_id),
    )


async def reset_running_sessions_on_startup(recovery_mode: bool = False) -> None:
    """
    On startup, all previously-running sessions have dead PTY fds.
    In recovery mode, mark as RECOVERY_PENDING so they can be re-spawned on demand.
    """
    target = SessionStatus.RECOVERY_PENDING.value if recovery_mode else SessionStatus.STOPPED.value
    await db.execute(
        "UPDATE sessions SET status = ? WHERE status IN (?, ?)",
        (target, SessionStatus.RUNNING.value, SessionStatus.PENDING.value),
    )


async def recover_session(session_id: str, user_id: int, recovery_data: dict) -> Session:
    """Re-spawn PTY for a RECOVERY_PENDING session and replay ring buffer."""
    import base64
    session = await get_session(session_id, user_id)
    if not session or session.status != SessionStatus.RECOVERY_PENDING:
        raise ValueError("Session not in recovery state")

    s = get_settings()
    preset = next((p for p in s.presets if p["name"] == session.image), None)
    if preset is None:
        raise ValueError(f"Unknown preset '{session.image}'")

    pid = pty_service.spawn(session_id, preset["command"], {}, session.cols, session.rows)
    await pty_broadcaster.ensure_reader(session_id)

    # Replay ring buffer into the broadcaster's state for the viewer
    session_recovery = recovery_data.get("sessions", {}).get(session_id, {})
    if session_recovery:
        state = pty_broadcaster._sessions.get(session_id)
        if state:
            for chunk_b64 in session_recovery.get("ring_buffer", []):
                state.ring_buffer.append(base64.b64decode(chunk_b64))

    await db.execute(
        "UPDATE sessions SET container_id = ?, status = ? WHERE id = ?",
        (str(pid), SessionStatus.RUNNING.value, session_id),
    )
    metrics.sessions_active.inc()
    row = await db.fetchone("SELECT * FROM sessions WHERE id = ?", (session_id,))
    return _row_to_session(row)
