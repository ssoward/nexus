"""Tests for the WebSocket single-use-token auth gate (app/routers/ws.py).

These cover the security-critical token validation directly: signature/type,
session binding, atomic single-use consume (replay defence), and expiry.
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.routers.ws import _validate_ws_token, _UUID_RE
from app.services.token_service import create_ws_token, create_access_token


async def _issue_ws_token(db, user_id, session_id):
    token, jti, expires_at = create_ws_token(user_id, session_id)
    await db.execute(
        "INSERT INTO ws_tokens (jti, user_id, session_id, expires_at) VALUES (?, ?, ?, ?)",
        (jti, user_id, session_id, expires_at.isoformat()),
    )
    return token, jti


SESSION_ID = "12345678-1234-1234-1234-123456789abc"


def test_uuid_regex_accepts_valid_and_rejects_bad():
    assert _UUID_RE.match(SESSION_ID)
    assert not _UUID_RE.match("not-a-uuid")
    assert not _UUID_RE.match("../etc/passwd")


class TestValidateWsToken:
    async def test_valid_token_returns_user_and_consumes(self, setup_db, test_user):
        token, jti = await _issue_ws_token(setup_db, test_user["id"], SESSION_ID)
        uid = await _validate_ws_token(token, SESSION_ID)
        assert uid == test_user["id"]
        # Token is now marked used
        row = await setup_db.fetchone("SELECT used FROM ws_tokens WHERE jti = ?", (jti,))
        assert row["used"] == 1

    async def test_replay_rejected(self, setup_db, test_user):
        token, _ = await _issue_ws_token(setup_db, test_user["id"], SESSION_ID)
        assert await _validate_ws_token(token, SESSION_ID) == test_user["id"]
        # Second use of the same token must fail (single-use)
        assert await _validate_ws_token(token, SESSION_ID) is None

    async def test_wrong_session_rejected(self, setup_db, test_user):
        token, _ = await _issue_ws_token(setup_db, test_user["id"], SESSION_ID)
        other = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert await _validate_ws_token(token, other) is None

    async def test_garbage_token_rejected(self, setup_db):
        assert await _validate_ws_token("not.a.jwt", SESSION_ID) is None

    async def test_access_token_rejected_on_ws(self, setup_db, test_user):
        """An access-token (type != 'ws') must not authenticate a websocket."""
        access = create_access_token(test_user["id"])
        assert await _validate_ws_token(access, SESSION_ID) is None

    async def test_expired_token_rejected(self, setup_db, test_user):
        token, jti = await _issue_ws_token(setup_db, test_user["id"], SESSION_ID)
        # Backdate the stored expiry
        past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        await setup_db.execute("UPDATE ws_tokens SET expires_at = ? WHERE jti = ?", (past, jti))
        assert await _validate_ws_token(token, SESSION_ID) is None

    async def test_unknown_jti_rejected(self, setup_db, test_user):
        """A validly-signed token with no matching ws_tokens row is rejected."""
        token, _, _ = create_ws_token(test_user["id"], SESSION_ID)  # not inserted
        assert await _validate_ws_token(token, SESSION_ID) is None
