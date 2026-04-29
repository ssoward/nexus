from datetime import datetime, timezone
from fastapi import Cookie, HTTPException, status
from typing import Optional

from app.database import db
from app.services.token_service import decode_access_token

_MAX_SESSION_SECONDS = 24 * 60 * 60  # 24-hour absolute session ceiling (MED-4)


async def get_current_user(access_token: Optional[str] = Cookie(default=None)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )
    if not access_token:
        raise credentials_exception

    payload = decode_access_token(access_token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    # MED-4: Enforce absolute session lifetime even on non-refresh requests.
    # auth_time is set at login and propagated unchanged through every refresh.
    auth_time = payload.get("auth_time")
    if auth_time and (datetime.now(timezone.utc).timestamp() - auth_time > _MAX_SESSION_SECONDS):
        raise credentials_exception

    # Check token revocation: reject tokens invalidated at logout
    jti = payload.get("jti")
    if jti:
        revoked = await db.fetchone(
            "SELECT jti FROM revoked_tokens WHERE jti = ?", (jti,)
        )
        if revoked:
            raise credentials_exception

    row = await db.fetchone(
        "SELECT id, username, lockout_until FROM users WHERE id = ?",
        (int(user_id),),
    )
    if row is None:
        raise credentials_exception

    # Enforce account lockout on already-issued tokens
    if row["lockout_until"]:
        lockout_until = datetime.fromisoformat(row["lockout_until"])
        if lockout_until.tzinfo is None:
            lockout_until = lockout_until.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < lockout_until:
            raise credentials_exception

    return row
