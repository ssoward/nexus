"""Tests for the PTY broadcaster (one reader → many subscribers, ring buffer).

The reader loop reads real bytes from an os.pipe, so pub/sub and buffering are
exercised end-to-end without a real terminal.
"""
import asyncio
import os

import pytest

from app.services import pty_broadcaster as bc


def _fresh(sid):
    bc._sessions.pop(sid, None)


class TestRingBuffer:
    def test_get_raw_buffer_empty_for_unknown(self):
        assert bc.get_raw_buffer("nope") == b""

    def test_get_raw_buffer_caps_bytes(self):
        sid = "ring-cap"
        _fresh(sid)
        bc.register(sid, -1)
        state = bc._sessions[sid]
        # Push more than REPLAY_MAX_BYTES worth of data
        chunk = b"x" * 1024
        for _ in range((bc.REPLAY_MAX_BYTES // 1024) + 50):
            state.ring_buffer.append(chunk)
        out = bc.get_raw_buffer(sid)
        assert len(out) <= bc.REPLAY_MAX_BYTES
        _fresh(sid)

    def test_get_buffer_last_n_lines(self):
        sid = "ring-lines"
        _fresh(sid)
        bc.register(sid, -1)
        bc._sessions[sid].ring_buffer.append(b"l1\nl2\nl3\nl4\nl5")
        out = bc.get_buffer(sid, last_n_lines=2)
        assert out == b"l4\nl5"
        _fresh(sid)


class TestSubscription:
    def test_subscribe_unknown_raises(self):
        with pytest.raises(KeyError):
            bc.subscribe("does-not-exist")

    def test_subscribe_cap_enforced(self):
        sid = "sub-cap"
        _fresh(sid)
        bc.register(sid, -1)
        queues = [bc.subscribe(sid) for _ in range(bc.MAX_SUBSCRIBERS_PER_SESSION)]
        assert len(queues) == bc.MAX_SUBSCRIBERS_PER_SESSION
        with pytest.raises(RuntimeError):
            bc.subscribe(sid)
        _fresh(sid)

    def test_unsubscribe_removes_queue(self):
        sid = "sub-remove"
        _fresh(sid)
        bc.register(sid, -1)
        q = bc.subscribe(sid)
        assert q in bc._sessions[sid].subscribers
        bc.unsubscribe(sid, q)
        assert q not in bc._sessions[sid].subscribers
        _fresh(sid)

    def test_broadcast_shutdown_signals_none(self):
        sid = "sub-shutdown"
        _fresh(sid)
        bc.register(sid, -1)
        q = bc.subscribe(sid)
        bc.broadcast_shutdown()
        assert q.get_nowait() is None
        _fresh(sid)


class TestReaderLoop:
    async def test_reader_broadcasts_and_signals_eof(self):
        sid = "reader-pipe"
        _fresh(sid)
        r, w = os.pipe()
        try:
            bc.register(sid, r)
            q = bc.subscribe(sid)
            await bc.ensure_reader(sid)

            os.write(w, b"hello-world")
            # Give the executor-based reader a moment to deliver
            chunk = await asyncio.wait_for(q.get(), timeout=2)
            assert chunk == b"hello-world"

            # Ring buffer should have captured it too
            assert b"hello-world" in bc.get_raw_buffer(sid)

            # Closing the write end → reader sees EOF → subscriber gets None
            os.close(w)
            w = None
            sentinel = await asyncio.wait_for(q.get(), timeout=2)
            assert sentinel is None
        finally:
            bc.unregister(sid)
            for fd in (r, w):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            _fresh(sid)
