"""
PTY process manager — spawns and tracks native terminal processes on the host.

Each session is an OS process attached to a PTY master/slave pair.
The master fd is kept open in this process; the browser sees its I/O via WebSocket.
Sessions survive browser disconnects; only explicit delete (or process exit) ends them.
"""
import fcntl
import logging
import os
import signal
import struct
import subprocess
import termios
import threading
from typing import Optional

from app.services import pty_broadcaster

logger = logging.getLogger(__name__)

# In-memory map: session_id → live session info
# This is intentionally not persisted — if the backend restarts, open fds are gone.
_active: dict[str, dict] = {}


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def _kill_with_sigkill(pid: int, proc: subprocess.Popen) -> None:
    """Background thread: sends SIGKILL if process survives 3 s after SIGTERM."""
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
    # Reap zombie
    try:
        os.waitpid(pid, os.WNOHANG)
    except (ChildProcessError, OSError):
        pass


def spawn(session_id: str, cmd: list[str], env: dict, cols: int, rows: int) -> int:
    """
    Spawn a PTY process on the host. Returns the child PID.
    Raises on failure.
    """
    master_fd, slave_fd = os.openpty()
    try:
        _set_winsize(slave_fd, rows, cols)

        env_merged = {**os.environ, **env, "TERM": "xterm-256color"}

        proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            env=env_merged,
            start_new_session=True,   # new process group / session
        )
    finally:
        os.close(slave_fd)           # parent doesn't need slave end

    _active[session_id] = {
        "pid": proc.pid,
        "master_fd": master_fd,
        "proc": proc,
    }
    pty_broadcaster.register(session_id, master_fd)
    logger.info("Spawned session %s: pid=%d cmd=%s", session_id[:8], proc.pid, cmd)
    return proc.pid


def get_fd(session_id: str) -> Optional[int]:
    """Return the master PTY fd for a session, or None if not active."""
    s = _active.get(session_id)
    return s["master_fd"] if s else None


def get_pid(session_id: str) -> Optional[int]:
    s = _active.get(session_id)
    return s["pid"] if s else None


def resize(session_id: str, cols: int, rows: int) -> None:
    s = _active.get(session_id)
    if s:
        try:
            _set_winsize(s["master_fd"], rows, cols)
        except OSError:
            pass
        # Explicitly send SIGWINCH so TUI apps (Claude Code) redraw at the new size
        try:
            os.kill(s["pid"], signal.SIGWINCH)
        except (ProcessLookupError, OSError):
            pass


def is_alive(session_id: str) -> bool:
    s = _active.get(session_id)
    if not s:
        return False
    return s["proc"].poll() is None


def kill(session_id: str) -> None:
    """Terminate the process and close the PTY fd. Safe to call multiple times."""
    s = _active.pop(session_id, None)
    if not s:
        return
    pty_broadcaster.unregister(session_id)
    pid = s["pid"]
    proc = s["proc"]
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass
    # Wait and SIGKILL in a background thread so we don't block the event loop (MED-7)
    threading.Thread(target=_kill_with_sigkill, args=(pid, proc), daemon=True).start()
    try:
        os.close(s["master_fd"])
    except OSError:
        pass
    logger.info("Killed session %s (pid=%d)", session_id[:8], pid)


def check_all() -> dict[str, bool]:
    """Return {session_id: is_alive} for all tracked sessions."""
    return {sid: is_alive(sid) for sid in list(_active)}


def kill_all(timeout: float = 5.0) -> None:
    """SIGTERM all PTY processes, wait up to timeout, SIGKILL stragglers."""
    import time as _time
    procs = []
    for session_id in list(_active):
        s = _active.get(session_id)
        if not s:
            continue
        try:
            os.kill(s["pid"], signal.SIGTERM)
            procs.append((session_id, s["pid"], s["proc"]))
        except (ProcessLookupError, OSError):
            pass

    deadline = _time.monotonic() + timeout
    for session_id, pid, proc in procs:
        remaining = max(0, deadline - _time.monotonic())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass

    for session_id in list(_active):
        s = _active.pop(session_id, None)
        if s:
            pty_broadcaster.unregister(session_id)
            try:
                os.close(s["master_fd"])
            except OSError:
                pass
    logger.info("kill_all: cleaned up %d sessions", len(procs))
