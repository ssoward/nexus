import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import db
from app.services import pty_service, pty_broadcaster, metrics
from app.services.rate_limiter import rate_limiter
from app.services.session_service import get_session, mark_active, update_session_status
from app.services.token_service import decode_ws_token
from app.models.session import SessionStatus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

_active_websockets: set[WebSocket] = set()


def get_active_websockets() -> set[WebSocket]:
    return set(_active_websockets)

PING_INTERVAL = 20
PONG_TIMEOUT = 30
OUTPUT_QUEUE_MAX = 500


async def _validate_ws_token(token: str, session_id: str) -> int | None:
    payload = decode_ws_token(token)
    if not payload:
        return None
    jti = payload.get("jti")
    if not jti or payload.get("session_id") != session_id:
        return None

    # Atomic consume: UPDATE … WHERE used=0 RETURNING guarantees only one
    # concurrent caller succeeds, closing the SELECT-then-UPDATE race window.
    row = await db.fetchone(
        "UPDATE ws_tokens SET used = 1 WHERE jti = ? AND used = 0 RETURNING user_id, expires_at",
        (jti,),
        commit=True,
    )
    if not row:
        return None

    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        return None
    return row["user_id"]


@router.websocket("/ws/session/{session_id}")
async def terminal_ws(websocket: WebSocket, session_id: str):
    token = websocket.query_params.get("token", "")
    user_id = await _validate_ws_token(token, session_id)
    if user_id is None:
        await websocket.close(code=4401, reason="Unauthorized")
        return

    session = await get_session(session_id, user_id)
    if session is None:
        await websocket.close(code=4404, reason="Session not found")
        return

    # If the session is stopped (process exited before), reject
    if session.status == SessionStatus.STOPPED or session.status == SessionStatus.ERROR:
        await websocket.close(code=4410, reason="Session stopped — restart it first")
        return

    # Recovery: re-spawn PTY on first WS connect after restart
    if session.status == SessionStatus.RECOVERY_PENDING:
        try:
            from app.services.recovery import load_recovery
            from app.services.session_service import recover_session
            from app.config import get_settings as _gs
            recovery_data = load_recovery(_gs().recovery_ttl_hours) or {}
            session = await recover_session(session_id, user_id, recovery_data)
            logger.info("Recovered session %s", session_id[:8])
        except Exception as e:
            logger.warning("Recovery failed for session %s: %s", session_id[:8], e)
            await update_session_status(session_id, SessionStatus.STOPPED)
            await websocket.close(code=4410, reason="Recovery failed — restart manually")
            return

    # Get (or lazily re-attach) the PTY fd
    master_fd = pty_service.get_fd(session_id)
    if master_fd is None:
        await update_session_status(session_id, SessionStatus.STOPPED)
        await websocket.close(code=4410, reason="Session process not attached — restart it")
        return

    await websocket.accept()
    _active_websockets.add(websocket)
    metrics.ws_connections_total.inc()
    metrics.ws_connections_active.inc()

    await db.execute(
        "INSERT INTO audit_log (user_id, action, detail, ip_address) VALUES (?, ?, ?, ?)",
        (user_id, "WS_CONNECT", json.dumps({"session_id": session_id}),
         websocket.client.host if websocket.client else None),
    )

    # Subscribe to the shared broadcaster — one PTY reader serves all connected tabs
    output_queue = pty_broadcaster.subscribe(session_id)
    loop = asyncio.get_event_loop()
    last_pong = loop.time()

    # ── WS writer: output_queue → browser ───────────────────────────────────
    async def _ws_writer():
        while True:
            chunk = await output_queue.get()
            if chunk is None:
                await websocket.send_text(json.dumps({
                    "type": "session_dead",
                    "reason": "Process exited",
                }))
                await update_session_status(session_id, SessionStatus.STOPPED)
                break
            await websocket.send_text(json.dumps({
                "type": "output",
                "data": base64.b64encode(chunk).decode(),
            }))
            await mark_active(session_id)

    # ── WS reader: browser → PTY ─────────────────────────────────────────────
    async def _ws_reader():
        nonlocal last_pong
        try:
            async for raw_msg in websocket.iter_text():
                try:
                    frame = json.loads(raw_msg)
                except json.JSONDecodeError:
                    continue

                ftype = frame.get("type")

                if ftype == "input":
                    data = frame.get("data", "")
                    if not data:
                        continue
                    if not await rate_limiter.allow(session_id, len(data)):
                        continue
                    encoded = data.encode()
                    await loop.run_in_executor(None, os.write, master_fd, encoded)

                elif ftype == "resize":
                    try:
                        cols = max(20, min(500, int(frame.get("cols", session.cols))))
                        rows = max(5, min(200, int(frame.get("rows", session.rows))))
                    except (ValueError, TypeError):
                        continue
                    pty_service.resize(session_id, cols, rows)

                elif ftype == "ping":
                    last_pong = loop.time()
                    await websocket.send_text(json.dumps({"type": "pong"}))

        except WebSocketDisconnect:
            pass

    async def _ping_monitor():
        while True:
            await asyncio.sleep(PING_INTERVAL)
            if loop.time() - last_pong > PONG_TIMEOUT:
                logger.info("Session %s ping timeout", session_id[:8])
                await websocket.close(code=4000, reason="Ping timeout")
                break

    writer_task = asyncio.create_task(_ws_writer(), name="ws_writer")
    ws_reader_task = asyncio.create_task(_ws_reader(), name="ws_reader")
    ping_task = asyncio.create_task(_ping_monitor(), name="ping_monitor")

    try:
        done, pending = await asyncio.wait(
            [writer_task, ws_reader_task, ping_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        finished = [t.get_name() for t in done]
        logger.info(
            "Session %s WS task finished: %s (pending: %s)",
            session_id[:8],
            finished,
            [t.get_name() for t in pending],
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    finally:
        _active_websockets.discard(websocket)
        metrics.ws_connections_active.dec()
        pty_broadcaster.unsubscribe(session_id, output_queue)
        rate_limiter.remove(session_id)
        await db.execute(
            "INSERT INTO audit_log (user_id, action, detail, ip_address) VALUES (?, ?, ?, ?)",
            (user_id, "WS_DISCONNECT", json.dumps({"session_id": session_id}),
             websocket.client.host if websocket.client else None),
        )
        logger.info("WS disconnected: session %s", session_id[:8])
