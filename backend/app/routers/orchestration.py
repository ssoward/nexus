import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from app.dependencies import get_current_user
from app.limiter import limiter
from app.models.session import SessionStatus
from app.services import pty_broadcaster, pty_service
from app.services.rate_limiter import rate_limiter
from app.services.session_service import get_session, list_sessions
from app.services.terminal_classifier import TerminalState, classify

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


# ── Request / response models ────────────────────────────────────────────────

class InputBody(BaseModel):
    data: str

    @field_validator("data")
    @classmethod
    def data_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("data must not be empty")
        if len(v) > 4096:
            raise ValueError("data must be <= 4096 characters")
        return v


class SessionStateResponse(BaseModel):
    session_id: str
    name: str
    state: TerminalState
    idle_seconds: float


class BufferResponse(BaseModel):
    session_id: str
    lines: int
    buffer: str


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_running_session(session_id: str, user_id: int):
    session = await get_session(session_id, user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.status != SessionStatus.RUNNING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is not running")
    return session


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/sessions/states", response_model=list[SessionStateResponse])
async def get_all_states(current_user: dict = Depends(get_current_user)):
    """Bulk: return classified state for all of the user's running sessions."""
    sessions = await list_sessions(current_user["id"])
    results = []
    for s in sessions:
        if s.status != SessionStatus.RUNNING:
            continue
        state, idle = classify(s.id)
        results.append(SessionStateResponse(
            session_id=s.id, name=s.name, state=state, idle_seconds=round(idle, 1),
        ))
    return results


@router.get("/sessions/{session_id}/state", response_model=SessionStateResponse)
async def get_session_state(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    session = await _get_running_session(session_id, current_user["id"])
    state, idle = classify(session_id)
    return SessionStateResponse(
        session_id=session_id, name=session.name, state=state, idle_seconds=round(idle, 1),
    )


@router.get("/sessions/{session_id}/buffer", response_model=BufferResponse)
async def get_session_buffer(
    session_id: str,
    lines: int = 100,
    current_user: dict = Depends(get_current_user),
):
    if lines < 1 or lines > 1000:
        raise HTTPException(400, "lines must be 1-1000")
    await _get_running_session(session_id, current_user["id"])
    raw = pty_broadcaster.get_buffer(session_id, last_n_lines=lines)
    return BufferResponse(
        session_id=session_id,
        lines=lines,
        buffer=raw.decode("utf-8", errors="replace"),
    )


@router.post("/sessions/{session_id}/input")
async def send_session_input(
    session_id: str,
    body: InputBody,
    current_user: dict = Depends(get_current_user),
):
    await _get_running_session(session_id, current_user["id"])
    master_fd = pty_service.get_fd(session_id)
    if master_fd is None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Session PTY not attached")

    if not await rate_limiter.allow(session_id, len(body.data)):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, os.write, master_fd, body.data.encode())
    return {"ok": True}
