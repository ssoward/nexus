"""
One PTY reader task per session; fans output to any number of WebSocket subscribers.

Without this, two browser tabs both calling os.read(master_fd) race for chunks —
each tab gets roughly half the output and appears broken.

Lifecycle
---------
register()       called by pty_service.spawn() — stores the fd, no task yet
ensure_reader()  called from async context after spawn (session_service) — starts the task
subscribe()      called per WebSocket connection — returns a dedicated output queue
unsubscribe()    called on WebSocket disconnect — removes the queue
unregister()     called by pty_service.kill() — cancels the task and cleans up
"""
import asyncio
import errno
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

OUTPUT_QUEUE_MAX = 500
MAX_SUBSCRIBERS_PER_SESSION = 5  # MED-8: cap concurrent viewers per session
RING_BUFFER_MAX = 1000  # chunks retained for replay / orchestration


@dataclass
class _State:
    master_fd: int
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    task: Optional[asyncio.Task] = None
    closed: bool = False
    ring_buffer: deque = field(default_factory=lambda: deque(maxlen=RING_BUFFER_MAX))
    last_output_time: float = 0.0  # monotonic time of last output


_sessions: dict[str, _State] = {}


# ── Lifecycle ────────────────────────────────────────────────────────────────

def register(session_id: str, master_fd: int) -> None:
    """Sync — safe to call from pty_service.spawn()."""
    _sessions[session_id] = _State(master_fd=master_fd)


def unregister(session_id: str) -> None:
    """Sync — safe to call from pty_service.kill()."""
    state = _sessions.pop(session_id, None)
    if state and state.task and not state.task.done():
        state.task.cancel()


async def ensure_reader(session_id: str) -> None:
    """Start the broadcast reader task if not already running.
    Must be called from an async context after spawn."""
    state = _sessions.get(session_id)
    if state and not state.closed and (state.task is None or state.task.done()):
        state.task = asyncio.create_task(_reader_loop(session_id))


# ── Pub/sub ──────────────────────────────────────────────────────────────────

def subscribe(session_id: str) -> asyncio.Queue:
    """Return a per-connection output queue. Caller must unsubscribe on disconnect."""
    state = _sessions.get(session_id)
    if state is None:
        raise KeyError(f"No broadcaster registered for session {session_id!r}")
    if not state.closed and len(state.subscribers) >= MAX_SUBSCRIBERS_PER_SESSION:
        raise RuntimeError(
            f"Maximum concurrent viewers ({MAX_SUBSCRIBERS_PER_SESSION}) reached for session {session_id!r}"
        )
    q: asyncio.Queue = asyncio.Queue(maxsize=OUTPUT_QUEUE_MAX)
    if state.closed:
        # PTY already dead — immediately signal the subscriber
        q.put_nowait(None)
    else:
        state.subscribers.add(q)
    return q


def unsubscribe(session_id: str, q: asyncio.Queue) -> None:
    state = _sessions.get(session_id)
    if state:
        state.subscribers.discard(q)


def broadcast_shutdown() -> None:
    """Signal all subscribers that their sessions are shutting down."""
    for session_id, state in _sessions.items():
        state.closed = True
        for q in list(state.subscribers):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
        state.subscribers.clear()


def get_raw_buffer(session_id: str) -> bytes:
    """Return the complete ring buffer contents as raw bytes for replay."""
    state = _sessions.get(session_id)
    if state is None:
        return b""
    return b"".join(state.ring_buffer)


def get_buffer(session_id: str, last_n_lines: int = 100) -> bytes:
    """Return the last N lines of terminal output from the ring buffer."""
    state = _sessions.get(session_id)
    if state is None:
        return b""
    raw = b"".join(state.ring_buffer)
    lines = raw.split(b"\n")
    return b"\n".join(lines[-last_n_lines:])


def get_last_output_time(session_id: str) -> float:
    """Return monotonic time of the last output chunk, or 0 if unknown."""
    state = _sessions.get(session_id)
    return state.last_output_time if state else 0.0


# ── Internal reader ──────────────────────────────────────────────────────────

async def _reader_loop(session_id: str) -> None:
    state = _sessions.get(session_id)
    if state is None:
        return

    master_fd = state.master_fd
    loop = asyncio.get_event_loop()

    def _read() -> bytes:
        try:
            return os.read(master_fd, 4096)
        except OSError as e:
            if e.errno in (errno.EIO, errno.EBADF, errno.EPIPE):
                return b""
            logger.warning("PTY read error session=%s: %s", session_id[:8], e)
            return b""

    logger.debug("PTY broadcaster started  session=%s", session_id[:8])

    while True:
        chunk = await loop.run_in_executor(None, _read)

        state = _sessions.get(session_id)
        if state is None:
            break

        if not chunk:
            # PTY closed — notify all subscribers and stop
            state.closed = True
            for q in list(state.subscribers):
                try:
                    q.put_nowait(None)
                except asyncio.QueueFull:
                    pass
            state.subscribers.clear()
            break

        from app.services.metrics import pty_bytes_read_total
        pty_bytes_read_total.inc(len(chunk))
        state.ring_buffer.append(chunk)
        state.last_output_time = time.monotonic()

        # Broadcast to every connected tab
        for q in list(state.subscribers):
            try:
                q.put_nowait(chunk)
            except asyncio.QueueFull:
                # Drop oldest chunk to make room for the newest
                try:
                    q.get_nowait()
                    q.put_nowait(chunk)
                except Exception:
                    pass

    logger.debug("PTY broadcaster stopped  session=%s", session_id[:8])
