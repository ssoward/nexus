import asyncio
import time
from typing import Dict, Tuple

# One input frame. A paste (a log, a diff, a long prompt) arrives as a single
# frame, so this is the paste size limit; the frontend checks the same number
# (MAX_PASTE_CHARS in frontend/src/components/terminal/paste.ts) and warns
# instead of sending.
MAX_INPUT_CHARS = 256_000
# Per-session budget per one-second window. Was 1000, which silently dropped
# any paste over ~1 KB that followed a keystroke within the same second; this
# only needs to stop a runaway client, not shape human input.
MAX_CHARS_PER_SECOND = 2 * MAX_INPUT_CHARS


class InputRateLimiter:
    def __init__(self) -> None:
        self._state: Dict[str, Tuple[int, float]] = {}  # session_id -> (char_count, window_start)
        self._lock = asyncio.Lock()

    async def allow(self, session_id: str, char_count: int) -> bool:
        """Returns True if the input is allowed, False if it should be dropped."""
        if char_count <= 0 or char_count > MAX_INPUT_CHARS:
            return False
        async with self._lock:
            now = time.monotonic()
            if session_id not in self._state:
                self._state[session_id] = (char_count, now)
                return True

            accumulated, window_start = self._state[session_id]

            if now - window_start >= 1.0:
                # New window
                self._state[session_id] = (char_count, now)
                return True

            new_total = accumulated + char_count
            if new_total > MAX_CHARS_PER_SECOND:
                return False

            self._state[session_id] = (new_total, window_start)
            return True

    def remove(self, session_id: str) -> None:
        self._state.pop(session_id, None)


# Module-level singleton
rate_limiter = InputRateLimiter()
