"""Simple in-process counters and gauges (no external dependencies)."""

import threading
import time


class _Counter:
    __slots__ = ("_value", "_lock")

    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()

    def inc(self, n: int = 1) -> None:
        with self._lock:
            self._value += n

    @property
    def value(self) -> int:
        return self._value


class _Gauge:
    __slots__ = ("_value", "_lock")

    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()

    def inc(self) -> None:
        with self._lock:
            self._value += 1

    def dec(self) -> None:
        with self._lock:
            self._value -= 1

    @property
    def value(self) -> int:
        return self._value


# ── Counters ─────────────────────────────────────────────────────────────────
sessions_created_total = _Counter()
ws_connections_total = _Counter()
pty_bytes_read_total = _Counter()

# ── Gauges ───────────────────────────────────────────────────────────────────
sessions_active = _Gauge()
ws_connections_active = _Gauge()

_startup_time = time.monotonic()


def uptime_seconds() -> float:
    return time.monotonic() - _startup_time
