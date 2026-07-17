"""Integration tests for the WebSocket handler (app/routers/ws.py:terminal_ws).

Rather than a sync TestClient (whose portal loop conflicts with the async
aiosqlite connection), we drive the real handler coroutine directly with a fake
WebSocket on the test's own event loop, backed by the real async DB. This covers
the handshake auth gates plus the live reader/writer/ping loop end-to-end.
"""
import asyncio
import uuid

import pytest
from fastapi import WebSocketDisconnect

from app.routers import ws as ws_module
from app.routers.ws import terminal_ws
from app.models.session import SessionStatus
from app.services.token_service import create_ws_token


VALID_SID = "12345678-1234-1234-1234-123456789abc"


class FakeWebSocket:
    """Minimal stand-in implementing only what terminal_ws touches."""

    def __init__(self, headers=None, query_params=None, inbound=None, hang_after=False):
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.client = type("Client", (), {"host": "127.0.0.1"})()
        self.accepted = False
        self.accept_subprotocol = "UNSET"
        self.closed = None  # (code, reason)
        self.sent = []
        self._inbound = list(inbound or [])
        self._hang_after = hang_after

    async def accept(self, subprotocol=None):
        self.accepted = True
        self.accept_subprotocol = subprotocol

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)

    async def send_text(self, data):
        self.sent.append(data)

    async def iter_text(self):
        for msg in self._inbound:
            yield msg
        if self._hang_after:
            # Keep the reader alive so another task (e.g. the writer) wins the race
            await asyncio.Event().wait()
        raise WebSocketDisconnect(code=1000)


async def _issue_token(db, user_id, session_id=VALID_SID):
    token, jti, expires_at = create_ws_token(user_id, session_id)
    await db.execute(
        "INSERT INTO ws_tokens (jti, user_id, session_id, expires_at) VALUES (?, ?, ?, ?)",
        (jti, user_id, session_id, expires_at.isoformat()),
    )
    return token


async def _insert_session(db, user_id, sid=VALID_SID, status=SessionStatus.RUNNING.value):
    await db.execute(
        "INSERT INTO sessions (id, user_id, name, image, container_name, status, cols, rows, "
        "created_at, last_active_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (sid, user_id, "s", "bash", f"session-{sid[:8]}", status, 80, 24),
    )


def _proto_headers(token):
    return {"sec-websocket-protocol": f"nexus-auth, {token}"}


class TestHandshakeGates:
    async def test_invalid_uuid_closed_4400(self, setup_db):
        wsk = FakeWebSocket()
        await terminal_ws(wsk, "not-a-uuid")
        assert wsk.closed[0] == 4400
        assert not wsk.accepted

    async def test_bad_token_closed_4401(self, setup_db):
        wsk = FakeWebSocket(headers=_proto_headers("garbage"))
        await terminal_ws(wsk, VALID_SID)
        assert wsk.closed[0] == 4401

    async def test_no_session_closed_4404(self, setup_db, test_user):
        token = await _issue_token(setup_db, test_user["id"])
        wsk = FakeWebSocket(headers=_proto_headers(token))
        await terminal_ws(wsk, VALID_SID)  # token valid, but no session row
        assert wsk.closed[0] == 4404

    async def test_stopped_session_closed_4410(self, setup_db, test_user):
        await _insert_session(setup_db, test_user["id"], status=SessionStatus.STOPPED.value)
        token = await _issue_token(setup_db, test_user["id"])
        wsk = FakeWebSocket(headers=_proto_headers(token))
        await terminal_ws(wsk, VALID_SID)
        assert wsk.closed[0] == 4410

    async def test_running_session_but_no_pty_fd_closed_4410(self, setup_db, test_user, monkeypatch):
        await _insert_session(setup_db, test_user["id"])
        token = await _issue_token(setup_db, test_user["id"])
        monkeypatch.setattr(ws_module.pty_service, "get_fd", lambda sid: None)
        wsk = FakeWebSocket(headers=_proto_headers(token))
        await terminal_ws(wsk, VALID_SID)
        assert wsk.closed[0] == 4410
        # Session should have been marked stopped
        row = await setup_db.fetchone("SELECT status FROM sessions WHERE id = ?", (VALID_SID,))
        assert row["status"] == SessionStatus.STOPPED.value


class TestLiveLoop:
    async def test_full_session_input_resize_ping(self, setup_db, test_user, monkeypatch):
        await _insert_session(setup_db, test_user["id"])
        token = await _issue_token(setup_db, test_user["id"])

        writes = []
        resizes = []
        monkeypatch.setattr(ws_module.pty_service, "get_fd", lambda sid: 7)
        monkeypatch.setattr(ws_module.pty_service, "write_all", lambda fd, data: writes.append((fd, data)))
        monkeypatch.setattr(ws_module.pty_service, "resize", lambda sid, cols, rows: resizes.append((cols, rows)))
        # subscribe returns an empty queue the writer will block on until cancelled
        monkeypatch.setattr(ws_module.pty_broadcaster, "subscribe", lambda sid: asyncio.Queue())
        monkeypatch.setattr(ws_module.pty_broadcaster, "unsubscribe", lambda sid, q: None)
        monkeypatch.setattr(ws_module.pty_broadcaster, "get_raw_buffer", lambda sid: b"prev-output")

        inbound = [
            '{"type":"input","data":"ls\\n"}',
            '{"type":"resize","cols":100,"rows":30}',
            '{"type":"ping"}',
            'not-json-should-be-ignored',
        ]
        wsk = FakeWebSocket(
            headers=_proto_headers(token),
            query_params={"replay": "1"},
            inbound=inbound,
        )

        await asyncio.wait_for(terminal_ws(wsk, VALID_SID), timeout=5)

        # Handshake accepted with echoed subprotocol
        assert wsk.accepted
        assert wsk.accept_subprotocol == "nexus-auth"
        # Replay buffer was sent before the live loop (base64 of the ring buffer)
        import base64 as _b64
        expected_replay = _b64.b64encode(b"prev-output").decode()
        assert any('"type": "output"' in s and expected_replay in s for s in wsk.sent)
        # Input reached the PTY, resize applied, ping answered with pong
        assert writes and writes[0][1] == b"ls\n"
        assert resizes and resizes[0] == (100, 30)
        assert any('"pong"' in s for s in wsk.sent)

    async def test_alt_screen_replay_repaints_instead_of_raw_dump(self, setup_db, test_user, monkeypatch):
        """In alt-screen mode, replay must NOT dump the raw ring buffer (which would
        overlay stale frames); it must SIGWINCH the app to force a clean repaint."""
        await _insert_session(setup_db, test_user["id"])
        token = await _issue_token(setup_db, test_user["id"])

        resizes = []
        monkeypatch.setattr(ws_module.pty_service, "get_fd", lambda sid: 7)
        monkeypatch.setattr(ws_module.pty_service, "resize", lambda sid, cols, rows: resizes.append((cols, rows)))
        monkeypatch.setattr(ws_module.pty_broadcaster, "subscribe", lambda sid: asyncio.Queue())
        monkeypatch.setattr(ws_module.pty_broadcaster, "unsubscribe", lambda sid, q: None)
        monkeypatch.setattr(ws_module.pty_broadcaster, "is_in_alt_screen", lambda sid: True)
        raw_calls = []
        monkeypatch.setattr(ws_module.pty_broadcaster, "get_raw_buffer",
                            lambda sid: raw_calls.append(sid) or b"SHOULD-NOT-BE-SENT")

        wsk = FakeWebSocket(
            headers=_proto_headers(token),
            query_params={"replay": "1"},
            inbound=[],
        )
        await asyncio.wait_for(terminal_ws(wsk, VALID_SID), timeout=5)

        # Raw buffer was never fetched/sent; a repaint SIGWINCH fired at session size
        assert raw_calls == []
        assert not any("SHOULD-NOT-BE-SENT" in s for s in wsk.sent)
        assert resizes and resizes[0] == (80, 24)

    async def test_process_exit_notifies_client_and_marks_stopped(self, setup_db, test_user, monkeypatch):
        await _insert_session(setup_db, test_user["id"])
        token = await _issue_token(setup_db, test_user["id"])
        monkeypatch.setattr(ws_module.pty_service, "get_fd", lambda sid: 7)
        # Queue pre-loaded with the None EOF sentinel → writer reports the process exit
        dead_queue = asyncio.Queue()
        dead_queue.put_nowait(None)
        monkeypatch.setattr(ws_module.pty_broadcaster, "subscribe", lambda sid: dead_queue)
        monkeypatch.setattr(ws_module.pty_broadcaster, "unsubscribe", lambda sid, q: None)

        wsk = FakeWebSocket(headers=_proto_headers(token), hang_after=True)
        await asyncio.wait_for(terminal_ws(wsk, VALID_SID), timeout=5)

        assert any('"session_dead"' in s for s in wsk.sent)
        row = await setup_db.fetchone("SELECT status FROM sessions WHERE id = ?", (VALID_SID,))
        assert row["status"] == SessionStatus.STOPPED.value

    async def test_token_is_single_use_across_connects(self, setup_db, test_user, monkeypatch):
        await _insert_session(setup_db, test_user["id"])
        token = await _issue_token(setup_db, test_user["id"])
        monkeypatch.setattr(ws_module.pty_service, "get_fd", lambda sid: 7)
        monkeypatch.setattr(ws_module.pty_broadcaster, "subscribe", lambda sid: asyncio.Queue())
        monkeypatch.setattr(ws_module.pty_broadcaster, "unsubscribe", lambda sid, q: None)

        first = FakeWebSocket(headers=_proto_headers(token))
        await asyncio.wait_for(terminal_ws(first, VALID_SID), timeout=5)
        assert first.accepted

        # Reusing the same token must be rejected at the auth gate
        second = FakeWebSocket(headers=_proto_headers(token))
        await terminal_ws(second, VALID_SID)
        assert second.closed[0] == 4401
