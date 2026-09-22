"""Tests for the PTY process manager.

Spawn tests use real short-lived host processes (`cat`, `true`) via os.openpty,
so they exercise the actual fork/exec + fd bookkeeping, not mocks.
"""
import os
import time
from unittest.mock import patch

import pytest

from app.services import pty_service, pty_broadcaster


def test_write_all_handles_partial_writes():
    """os.write may write fewer bytes than requested; write_all must loop."""
    calls = []
    original = b"abcdefghij"  # 10 bytes

    def fake_write(fd, data):
        # Simulate the kernel accepting only 3 bytes per call
        chunk = bytes(data[:3])
        calls.append(chunk)
        return len(chunk)

    with patch("app.services.pty_service.os.write", side_effect=fake_write):
        pty_service.write_all(7, original)

    # Every byte delivered, in order, across multiple writes
    assert b"".join(calls) == original
    assert len(calls) == 4  # 3+3+3+1


def test_write_all_single_write():
    with patch("app.services.pty_service.os.write", return_value=5) as mock:
        pty_service.write_all(3, b"hello")
    mock.assert_called_once()


class TestSpawnLifecycle:
    def teardown_method(self):
        # Ensure no stray processes/fds leak between tests
        for sid in list(pty_service._active):
            pty_service.kill(sid)

    def test_spawn_get_fd_pid_and_alive(self):
        sid = "test-cat-session"
        pid = pty_service.spawn(sid, ["cat"], {}, 80, 24)
        try:
            assert isinstance(pid, int) and pid > 0
            assert pty_service.get_pid(sid) == pid
            fd = pty_service.get_fd(sid)
            assert isinstance(fd, int)
            assert pty_service.is_alive(sid) is True
        finally:
            pty_service.kill(sid)

    def test_write_all_reaches_pty(self):
        """cat echoes stdin back on the PTY — verify write_all delivers bytes."""
        sid = "test-echo-session"
        pty_service.spawn(sid, ["cat"], {}, 80, 24)
        try:
            fd = pty_service.get_fd(sid)
            pty_service.write_all(fd, b"ping\n")
            time.sleep(0.3)
            os.set_blocking(fd, False)
            data = b""
            for _ in range(5):
                try:
                    data += os.read(fd, 1024)
                except BlockingIOError:
                    time.sleep(0.1)
                if b"ping" in data:
                    break
            assert b"ping" in data
        finally:
            pty_service.kill(sid)

    def test_resize_does_not_raise(self):
        sid = "test-resize-session"
        pty_service.spawn(sid, ["cat"], {}, 80, 24)
        try:
            pty_service.resize(sid, 120, 40)  # should not raise
        finally:
            pty_service.kill(sid)

    def test_kill_is_idempotent_and_clears_state(self):
        sid = "test-kill-session"
        pty_service.spawn(sid, ["cat"], {}, 80, 24)
        pty_service.kill(sid)
        assert pty_service.get_fd(sid) is None
        assert pty_service.is_alive(sid) is False
        pty_service.kill(sid)  # second call is a no-op, must not raise

    def test_exited_process_reports_not_alive(self):
        sid = "test-true-session"
        pty_service.spawn(sid, ["true"], {}, 80, 24)  # exits immediately
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and pty_service.is_alive(sid):
                time.sleep(0.05)
            assert pty_service.is_alive(sid) is False
        finally:
            pty_service.kill(sid)

    def test_secrets_stripped_from_child_env(self):
        """JWT_SECRET/APP_SECRET etc. must never reach a spawned shell."""
        with patch.dict(os.environ, {"JWT_SECRET": "leak-me", "PATH": os.environ.get("PATH", "")}):
            captured = {}

            real_popen = pty_service.subprocess.Popen

            def spy_popen(*args, **kwargs):
                captured.update(kwargs.get("env", {}))
                return real_popen(*args, **kwargs)

            sid = "test-env-session"
            with patch("app.services.pty_service.subprocess.Popen", side_effect=spy_popen):
                pty_service.spawn(sid, ["cat"], {}, 80, 24)
            try:
                assert "JWT_SECRET" not in captured
                assert captured.get("TERM") == "xterm-256color"
            finally:
                pty_service.kill(sid)


class TestChildEnvAllowlist:
    """Sessions get an allowlisted environment, not everything the backend has (M5)."""

    def _spawn_and_capture(self, env_patch: dict) -> dict:
        from unittest.mock import patch
        import os as _os
        from app.services import pty_service as _pty
        captured: dict = {}
        real_popen = _pty.subprocess.Popen

        def spy_popen(*args, **kwargs):
            captured.update(kwargs.get("env", {}))
            return real_popen(*args, **kwargs)

        sid = "test-allowlist-session"
        with patch.dict(_os.environ, {**env_patch, "PATH": _os.environ.get("PATH", "")}):
            with patch("app.services.pty_service.subprocess.Popen", side_effect=spy_popen):
                _pty.spawn(sid, ["cat"], {}, 80, 24)
        _pty.kill(sid)
        return captured

    def test_unlisted_backend_vars_do_not_reach_the_shell(self):
        env = self._spawn_and_capture({"SMTP_USER": "ops@example.com", "SOME_RANDOM_TOKEN": "x", "HOME": "/tmp/h"})
        assert "SMTP_USER" not in env
        assert "SOME_RANDOM_TOKEN" not in env
        assert env.get("HOME") == "/tmp/h"
        assert "PATH" in env
        assert env.get("TERM") == "xterm-256color"

    def test_lc_and_xdg_prefixes_pass(self):
        env = self._spawn_and_capture({"LC_ALL": "C.UTF-8", "XDG_CONFIG_HOME": "/tmp/xdg"})
        assert env.get("LC_ALL") == "C.UTF-8"
        assert env.get("XDG_CONFIG_HOME") == "/tmp/xdg"

    def test_configured_pass_env_is_forwarded(self, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "session_pass_env", ["ANTHROPIC_API_KEY"])
        env = self._spawn_and_capture({"ANTHROPIC_API_KEY": "sk-ant-test", "DEEPSEEK_API_KEY": "nope"})
        assert env.get("ANTHROPIC_API_KEY") == "sk-ant-test"
        assert "DEEPSEEK_API_KEY" not in env

    def test_pass_env_cannot_leak_backend_secrets(self, monkeypatch):
        """Even an explicit pass_env entry never forwards the signing/encryption secrets."""
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "session_pass_env", ["JWT_SECRET"])
        env = self._spawn_and_capture({"JWT_SECRET": "leak-me"})
        assert "JWT_SECRET" not in env
