import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from typing import List

from app.config import get_settings
from app.database import db
from app.dependencies import get_current_user
from app.models.session import SessionCreate, SessionPublic, SessionResizeRequest, SessionStatus
from app.services import session_service, pty_service, pty_broadcaster

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _to_public(s) -> SessionPublic:
    return SessionPublic(
        id=s.id,
        name=s.name,
        image=s.image,
        status=s.status,
        cols=s.cols,
        rows=s.rows,
        created_at=s.created_at,
        last_active_at=s.last_active_at,
    )


@router.get("", response_model=List[SessionPublic])
async def list_sessions(current_user: dict = Depends(get_current_user)):
    sessions = await session_service.list_sessions(current_user["id"])
    # The process_watchdog is responsible for detecting dead processes and
    # updating status.  Doing it here caused a race: the poll response
    # marked sessions STOPPED → the frontend unmounted the pane → the WS
    # closed → the PTY was killed, even though the process was still alive.
    return [_to_public(s) for s in sessions]


@router.post("", response_model=SessionPublic, status_code=status.HTTP_201_CREATED)
async def create_session(
    req: SessionCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    s = get_settings()
    existing = await session_service.list_sessions(current_user["id"])
    running = [x for x in existing if x.status == SessionStatus.RUNNING]
    if len(running) >= s.max_panes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Maximum of {s.max_panes} concurrent sessions reached",
        )

    ip = request.client.host if request.client else None
    session = await session_service.create_session(current_user["id"], req, ip)
    return _to_public(session)


@router.post("/{session_id}/restart", response_model=SessionPublic)
async def restart_session(
    session_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Re-spawn the process for a stopped/error session."""
    session = await session_service.get_session(session_id, current_user["id"])
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.status == SessionStatus.RUNNING and pty_service.is_alive(session_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session already running")

    s = get_settings()
    preset = next((p for p in s.presets if p["name"] == session.image), None)
    if preset is None:
        raise HTTPException(status_code=400, detail="Session references an unknown preset")

    pty_service.kill(session_id)  # clean up any stale fd
    try:
        pid = pty_service.spawn(session_id, preset["command"], {}, session.cols, session.rows)
        await pty_broadcaster.ensure_reader(session_id)
        await db.execute(
            "UPDATE sessions SET container_id = ?, status = ? WHERE id = ?",
            (str(pid), SessionStatus.RUNNING.value, session_id),
        )
    except Exception as e:
        logger.exception("Failed to restart session %s: %s", session_id[:8], e)
        await db.execute(
            "UPDATE sessions SET status = ? WHERE id = ?",
            (SessionStatus.ERROR.value, session_id),
        )
        raise HTTPException(status_code=500, detail="Failed to restart session")

    row = await db.fetchone("SELECT * FROM sessions WHERE id = ?", (session_id,))
    from app.services.session_service import _row_to_session
    return _to_public(_row_to_session(row))


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    session = await session_service.get_session(session_id, current_user["id"])
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    ip = request.client.host if request.client else None
    await session_service.delete_session(session_id, current_user["id"], ip)


@router.patch("/{session_id}/resize", status_code=status.HTTP_204_NO_CONTENT)
async def resize_session(
    session_id: str,
    req: SessionResizeRequest,
    current_user: dict = Depends(get_current_user),
):
    session = await session_service.get_session(session_id, current_user["id"])
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    pty_service.resize(session_id, req.cols, req.rows)
    await db.execute(
        "UPDATE sessions SET cols = ?, rows = ? WHERE id = ?",
        (req.cols, req.rows, session_id),
    )
