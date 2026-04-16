import asyncio
import time
from typing import Dict, Tuple

MAX_CHARS_PER_SECOND = 1000


class InputRateLimiter:
    def __init__(self) -> None:
        self._state: Dict[str, Tuple[int, float]] = {}  # session_id -> (char_count, window_start)
        self._lock = asyncio.Lock()

    async def allow(self, session_id: str, char_count: int) -> bool:
        """Returns True if the input is allowed, False if it should be dropped."""
        if char_count <= 0 or char_count > 10_000:
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
