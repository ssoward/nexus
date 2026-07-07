"""Tests for encrypted session-recovery serialization (M1)."""
import json
import os
from collections import deque

import pytest

from app.crypto import decrypt_bytes, encrypt_bytes
from app.services import recovery, pty_broadcaster


def test_encrypt_decrypt_roundtrip():
    blob = encrypt_bytes(b"top secret scrollback", "recovery")
    assert blob != b"top secret scrollback"
    assert decrypt_bytes(blob, "recovery") == b"top secret scrollback"


def test_wrong_context_fails_decrypt():
    from cryptography.exceptions import InvalidTag
    blob = encrypt_bytes(b"data", "recovery")
    with pytest.raises(InvalidTag):
        decrypt_bytes(blob, "other")


def _make_state(chunks):
    state = pty_broadcaster._State(master_fd=-1)
    state.ring_buffer = deque(chunks)
    return state


def test_save_recovery_writes_encrypted_file(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, "RECOVERY_DIR", str(tmp_path))
    monkeypatch.setattr(recovery, "RECOVERY_FILE", str(tmp_path / "recovery.enc"))
    monkeypatch.setattr(recovery, "_LEGACY_PLAINTEXT_FILE", str(tmp_path / "recovery.json"))
    monkeypatch.setattr(
        pty_broadcaster, "_sessions",
        {"sess-1": _make_state([b"secret-token=abc123\n"])},
    )

    recovery.save_recovery()

    raw = (tmp_path / "recovery.enc").read_bytes()
    # The sensitive scrollback must not be present in plaintext on disk
    assert b"secret-token" not in raw
    # But a round-trip load recovers it
    data = recovery.load_recovery(ttl_hours=24)
    assert "sess-1" in data["sessions"]


def test_save_removes_legacy_plaintext(tmp_path, monkeypatch):
    legacy = tmp_path / "recovery.json"
    legacy.write_text('{"leftover": true}')
    monkeypatch.setattr(recovery, "RECOVERY_DIR", str(tmp_path))
    monkeypatch.setattr(recovery, "RECOVERY_FILE", str(tmp_path / "recovery.enc"))
    monkeypatch.setattr(recovery, "_LEGACY_PLAINTEXT_FILE", str(legacy))
    monkeypatch.setattr(pty_broadcaster, "_sessions", {})

    recovery.save_recovery()
    assert not legacy.exists()


def test_load_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, "RECOVERY_FILE", str(tmp_path / "nope.enc"))
    assert recovery.load_recovery(ttl_hours=24) is None


def test_load_expired_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, "RECOVERY_DIR", str(tmp_path))
    monkeypatch.setattr(recovery, "RECOVERY_FILE", str(tmp_path / "recovery.enc"))
    monkeypatch.setattr(recovery, "_LEGACY_PLAINTEXT_FILE", str(tmp_path / "recovery.json"))
    monkeypatch.setattr(pty_broadcaster, "_sessions", {})
    recovery.save_recovery()

    # A 0-hour TTL makes any saved file immediately stale
    assert recovery.load_recovery(ttl_hours=0) is None
    assert not (tmp_path / "recovery.enc").exists()  # stale file is removed
