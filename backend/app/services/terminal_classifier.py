"""
Classify terminal session state by analysing recent output.

States:
  WORKING  — actively producing output (< 3 s since last chunk)
  WAITING  — at a shell/REPL prompt, idle
  ASKING   — a tool or agent is asking the user a question
  BUSY     — process running but no recent output
"""

import re
import time
from enum import Enum

from app.services import pty_broadcaster

# ── Constants ────────────────────────────────────────────────────────────────

WORKING_THRESHOLD = 3.0  # seconds

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b\[[\d;]*m")

_PROMPT_PATTERNS = [
    re.compile(r"[$#%>»] \s*$"),         # sh / bash / zsh / fish
    re.compile(r">>> \s*$"),              # Python REPL
    re.compile(r"\.\.\. \s*$"),           # Python continuation
    re.compile(r"In \[\d+\]: \s*$"),      # IPython
    re.compile(r"irb.*> \s*$"),           # Ruby
]

_QUESTION_PATTERNS = [
    re.compile(r"\(y/n\)", re.IGNORECASE),
    re.compile(r"\[Y/n\]|\[y/N\]", re.IGNORECASE),
    re.compile(r"\?\s*$"),
    re.compile(r"(Do you want|Would you like|Allow|Approve|Confirm|Continue)", re.IGNORECASE),
    re.compile(r"Press (Enter|any key)", re.IGNORECASE),
]


class TerminalState(str, Enum):
    WORKING = "WORKING"
    WAITING = "WAITING"
    ASKING = "ASKING"
    BUSY = "BUSY"


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def classify(session_id: str) -> tuple[TerminalState, float]:
    """Return (state, idle_seconds) for a session."""
    last_time = pty_broadcaster.get_last_output_time(session_id)
    if last_time == 0:
        return TerminalState.BUSY, 0.0

    idle_seconds = time.monotonic() - last_time

    if idle_seconds < WORKING_THRESHOLD:
        return TerminalState.WORKING, idle_seconds

    # Analyse the last few lines of output
    raw = pty_broadcaster.get_buffer(session_id, last_n_lines=5)
    text = _strip_ansi(raw.decode("utf-8", errors="replace"))
    last_line = text.rstrip().rsplit("\n", 1)[-1] if text.strip() else ""

    for pat in _QUESTION_PATTERNS:
        if pat.search(last_line):
            return TerminalState.ASKING, idle_seconds

    for pat in _PROMPT_PATTERNS:
        if pat.search(last_line):
            return TerminalState.WAITING, idle_seconds

    return TerminalState.BUSY, idle_seconds
