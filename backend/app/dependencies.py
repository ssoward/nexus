from datetime import datetime, timezone
from fastapi import Cookie, HTTPException, status
from typing import Optional

from app.database import db
from app.services.token_service import decode_access_token


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

    # auth_time is set at login and propagated unchanged through every refresh.
    # There is no absolute session ceiling — sessions live until explicit logout
    # (or global eviction via tokens_valid_after below).
    auth_time = payload.get("auth_time")

    # Check token revocation: reject tokens invalidated at logout
    jti = payload.get("jti")
    if jti:
        revoked = await db.fetchone(
            "SELECT jti FROM revoked_tokens WHERE jti = ?", (jti,)
        )
        if revoked:
            raise credentials_exception

    row = await db.fetchone(
        "SELECT id, username, lockout_until, tokens_valid_after FROM users WHERE id = ?",
        (int(user_id),),
    )
    if row is None:
        raise credentials_exception

    # Per-user token invalidation: password change, email change, and MFA recovery
    # stamp tokens_valid_after. Any token whose auth_time predates that stamp is dead,
    # so those events evict every outstanding session — not just the current cookie.
    tva = row["tokens_valid_after"]
    if tva:
        cutoff = datetime.fromisoformat(tva)
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        if auth_time is None or auth_time < cutoff.timestamp():
            raise credentials_exception

    # Enforce account lockout on already-issued tokens
    if row["lockout_until"]:
        lockout_until = datetime.fromisoformat(row["lockout_until"])
        if lockout_until.tzinfo is None:
            lockout_until = lockout_until.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < lockout_until:
            raise credentials_exception

    return row
