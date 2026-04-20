import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt

from app.config import get_settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: int, auth_time: float | None = None) -> str:
    s = get_settings()
    now = _utcnow()
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=s.jwt_expire_minutes),
        "jti": str(uuid.uuid4()),
        "auth_time": auth_time or now.timestamp(),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
        if payload.get("type") == "ws":
            return None
        return payload
    except jwt.PyJWTError:
        return None


def create_ws_token(user_id: int, session_id: str) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at)."""
    s = get_settings()
    now = _utcnow()
    expires_at = now + timedelta(seconds=s.ws_token_expire_seconds)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),
        "session_id": session_id,
        "iat": now,
        "exp": expires_at,
        "jti": jti,
        "type": "ws",
    }
    token = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)
    return token, jti, expires_at


def decode_ws_token(token: str) -> Optional[dict]:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
        if payload.get("type") != "ws":
            return None
        return payload
    except jwt.PyJWTError:
        return None
