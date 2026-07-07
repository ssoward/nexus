"""Tests for the process-watchdog maintenance sweeps."""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from app.services import process_watchdog as wd
from app.models.session import SessionStatus


async def _insert_session(db, user_id, status, last_active=None, name="s"):
    sid = str(uuid.uuid4())
    la = last_active or datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO sessions (id, user_id, name, image, container_name, status, cols, rows, "
        "created_at, last_active_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (sid, user_id, name, "bash", f"session-{sid[:8]}", status, 80, 24,
         datetime.now(timezone.utc).isoformat(), la),
    )
    return sid


class TestSweepDeadProcesses:
    async def test_dead_running_session_marked_stopped(self, setup_db, test_user):
        sid = await _insert_session(setup_db, test_user["id"], SessionStatus.RUNNING.value)
        with (
            patch("app.services.pty_service.check_all", return_value={sid: False}),
            patch("app.services.pty_service.kill") as mock_kill,
        ):
            await wd.sweep_dead_processes(setup_db)
        row = await setup_db.fetchone("SELECT status FROM sessions WHERE id = ?", (sid,))
        assert row["status"] == SessionStatus.STOPPED.value
        mock_kill.assert_called_once_with(sid)

    async def test_alive_session_left_running(self, setup_db, test_user):
        sid = await _insert_session(setup_db, test_user["id"], SessionStatus.RUNNING.value)
        with (
            patch("app.services.pty_service.check_all", return_value={sid: True}),
            patch("app.services.pty_service.kill") as mock_kill,
        ):
            await wd.sweep_dead_processes(setup_db)
        row = await setup_db.fetchone("SELECT status FROM sessions WHERE id = ?", (sid,))
        assert row["status"] == SessionStatus.RUNNING.value
        mock_kill.assert_not_called()


class TestSweepIdleSessions:
    async def test_disabled_when_timeout_zero(self, setup_db, test_user):
        old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        sid = await _insert_session(setup_db, test_user["id"], SessionStatus.RUNNING.value, last_active=old)
        with patch("app.services.pty_service.kill") as mock_kill:
            await wd.sweep_idle_sessions(setup_db, 0)
        mock_kill.assert_not_called()
        row = await setup_db.fetchone("SELECT status FROM sessions WHERE id = ?", (sid,))
        assert row["status"] == SessionStatus.RUNNING.value

    async def test_idle_session_stopped(self, setup_db, test_user):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        sid = await _insert_session(setup_db, test_user["id"], SessionStatus.RUNNING.value, last_active=old)
        with patch("app.services.pty_service.kill") as mock_kill:
            await wd.sweep_idle_sessions(setup_db, 3600)  # 1h timeout, session idle 2h
        mock_kill.assert_called_once_with(sid)
        row = await setup_db.fetchone("SELECT status FROM sessions WHERE id = ?", (sid,))
        assert row["status"] == SessionStatus.STOPPED.value

    async def test_recent_session_kept(self, setup_db, test_user):
        recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        sid = await _insert_session(setup_db, test_user["id"], SessionStatus.RUNNING.value, last_active=recent)
        with patch("app.services.pty_service.kill") as mock_kill:
            await wd.sweep_idle_sessions(setup_db, 3600)
        mock_kill.assert_not_called()


class TestCleanupExpiredTokens:
    async def test_purges_expired_and_keeps_valid(self, setup_db, test_user):
        uid = test_user["id"]
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        # ws_tokens: one expired, one valid
        await setup_db.execute(
            "INSERT INTO ws_tokens (jti, user_id, session_id, expires_at) VALUES (?, ?, ?, ?)",
            ("expired-jti", uid, "sess", past),
        )
        await setup_db.execute(
            "INSERT INTO ws_tokens (jti, user_id, session_id, expires_at) VALUES (?, ?, ?, ?)",
            ("valid-jti", uid, "sess", future),
        )
        # revoked_tokens: one expired
        await setup_db.execute(
            "INSERT INTO revoked_tokens (jti, user_id, expires_at) VALUES (?, ?, ?)",
            ("rev-old", uid, past),
        )
        # recovery token expired > 1h ago
        old_recovery = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        await setup_db.execute(
            "INSERT INTO account_recovery_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (uid, "hash", old_recovery),
        )

        await wd.cleanup_expired_tokens(setup_db)

        ws = await setup_db.fetchall("SELECT jti FROM ws_tokens", ())
        assert [r["jti"] for r in ws] == ["valid-jti"]
        rev = await setup_db.fetchall("SELECT jti FROM revoked_tokens", ())
        assert rev == []
        rec = await setup_db.fetchall("SELECT id FROM account_recovery_tokens", ())
        assert rec == []
