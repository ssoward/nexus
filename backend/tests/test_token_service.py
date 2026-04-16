"""Unit tests for JWT token creation and validation."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import get_settings
from app.services.token_service import (
    create_access_token,
    create_ws_token,
    decode_access_token,
    decode_ws_token,
)


def test_create_and_decode_access_token():
    token = create_access_token(42)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert "jti" in payload
    assert "exp" in payload
    assert "iat" in payload


def test_access_token_jti_is_unique():
    t1 = create_access_token(1)
    t2 = create_access_token(1)
    p1 = decode_access_token(t1)
    p2 = decode_access_token(t2)
    assert p1["jti"] != p2["jti"]


def test_decode_invalid_token_returns_none():
    assert decode_access_token("not.a.valid.token") is None


def test_decode_tampered_token_returns_none():
    token = create_access_token(1)
    tampered = token[:-5] + "XXXXX"
    assert decode_access_token(tampered) is None


def test_decode_expired_token_returns_none():
    s = get_settings()
    expired_payload = {
        "sub": "1",
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "jti": str(uuid.uuid4()),
    }
    expired_token = jwt.encode(expired_payload, s.jwt_secret, algorithm=s.jwt_algorithm)
    assert decode_access_token(expired_token) is None


def test_create_and_decode_ws_token():
    token, jti, expires_at = create_ws_token(7, "session-abc")
    payload = decode_ws_token(token)
    assert payload is not None
    assert payload["sub"] == "7"
    assert payload["session_id"] == "session-abc"
    assert payload["type"] == "ws"
    assert payload["jti"] == jti


def test_ws_token_includes_expiry():
    _, _, expires_at = create_ws_token(1, "s")
    assert expires_at > datetime.now(timezone.utc)


def test_decode_ws_token_rejects_access_token():
    """An access token must not pass ws-token validation (missing 'type' field)."""
    access_token = create_access_token(1)
    assert decode_ws_token(access_token) is None


def test_decode_access_token_accepts_ws_token_structurally():
    """
    decode_access_token does not check 'type', so it will parse a ws token.
    This is acceptable — enforcement of type happens at the ws endpoint level.
    The important direction is that decode_ws_token rejects access tokens.
    """
    ws_token, _, _ = create_ws_token(1, "s")
    payload = decode_access_token(ws_token)
    # Structurally valid JWT with same secret — parses fine
    assert payload is not None
    assert payload.get("type") == "ws"
