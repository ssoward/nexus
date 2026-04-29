import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import pyotp

from app.database import db
from app.crypto import verify_password, decrypt_totp_secret
from app.models.audit import AuditAction

logger = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

# Timing-safe rejection: always run bcrypt even for unknown users (HIGH-2)
_DUMMY_HASH = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMUfOcHbAKKX3FyD0KFWL6oiW."

# Sentinel: password correct but TOTP code not yet provided
NEEDS_TOTP = "NEEDS_TOTP"

# Sentinel: password correct but no MFA configured yet — setup required
NEEDS_MFA_SETUP = "NEEDS_MFA_SETUP"
NEEDS_TOTP_SETUP = NEEDS_MFA_SETUP  # backward compat alias

# Sentinel: password correct, email OTP sent, awaiting code
NEEDS_EMAIL_OTP = "NEEDS_EMAIL_OTP"

# Sentinel: password correct, passkey assertion required
NEEDS_PASSKEY = "NEEDS_PASSKEY"


async def _write_audit(
    user_id: Optional[int],
    action: AuditAction,
    detail: Optional[dict],
    ip: Optional[str],
) -> None:
    # Never log secrets — filter any suspicious keys
    safe_detail = None
    if detail:
        safe_detail = {
            k: v for k, v in detail.items()
            if not any(s in k.lower() for s in ["secret", "password", "token", "key"])
        }
    await db.execute(
        "INSERT INTO audit_log (user_id, action, detail, ip_address) VALUES (?, ?, ?, ?)",
        (user_id, action.value, json.dumps(safe_detail) if safe_detail else None, ip),
    )


async def authenticate_user(
    username: str,
    password: str,
    totp_code: str,
    ip: Optional[str],
) -> Optional[dict] | str:
    """
    Returns:
      - user row dict on full success
      - NEEDS_TOTP sentinel when password is correct but TOTP required and not provided
      - None on failure
    Handles lockout tracking, TOTP verification, and audit logging.
    """
    row = await db.fetchone(
        "SELECT id, username, hashed_password, failed_login_count, lockout_until, "
        "encrypted_totp_secret, last_totp_code, last_totp_at, mfa_method FROM users WHERE username = ?",
        (username,),
    )

    if row is None:
        # Timing attack defence: always burn bcrypt time for unknown users (HIGH-2)
        verify_password(password, _DUMMY_HASH)
        await _write_audit(None, AuditAction.LOGIN_FAILURE, {"reason": "unknown_user"}, ip)
        return None

    user_id = row["id"]

    # Check account lockout
    if row["lockout_until"]:
        lockout_until = datetime.fromisoformat(row["lockout_until"])
        if lockout_until.tzinfo is None:
            lockout_until = lockout_until.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < lockout_until:
            await _write_audit(
                user_id, AuditAction.LOGIN_LOCKED,
                {"lockout_until": str(lockout_until)}, ip,
            )
            return None

    # Verify password
    if not verify_password(password, row["hashed_password"]):
        await _increment_failed_login(user_id, ip)
        return None

    mfa_method = row.get("mfa_method")

    # No MFA configured — user must set up before they can log in
    if mfa_method is None:
        return NEEDS_MFA_SETUP

    # ── TOTP path ────────────────────────────────────────────────────────
    if mfa_method == "totp":
        if not totp_code:
            return NEEDS_TOTP
        try:
            secret = decrypt_totp_secret(bytes(row["encrypted_totp_secret"]), user_id)
        except Exception:
            await _write_audit(user_id, AuditAction.LOGIN_FAILURE, {"reason": "totp_decrypt_error"}, ip)
            return None
        if not pyotp.TOTP(secret).verify(totp_code, valid_window=1):
            await _increment_failed_login(user_id, ip)
            return None
        # Replay protection
        REPLAY_WINDOW = timedelta(seconds=90)
        last_code = row.get("last_totp_code")
        last_at_str = row.get("last_totp_at")
        if last_code and last_code == totp_code and last_at_str:
            last_at = datetime.fromisoformat(last_at_str)
            if last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - last_at < REPLAY_WINDOW:
                await _write_audit(user_id, AuditAction.LOGIN_FAILURE, {"reason": "totp_replay"}, ip)
                return None
        await db.execute(
            "UPDATE users SET last_totp_code = ?, last_totp_at = ? WHERE id = ?",
            (totp_code, datetime.now(timezone.utc).isoformat(), user_id),
        )

    # ── Passkey path ─────────────────────────────────────────────────────
    elif mfa_method == "passkey":
        # Passkey assertion is handled by /api/auth/passkey/authenticate/begin+complete
        return NEEDS_PASSKEY

    # ── Email OTP path ───────────────────────────────────────────────────
    elif mfa_method == "email_otp":
        if not totp_code:
            # Send OTP (won't re-send if a valid code already exists)
            from app.services.otp_service import send_email_otp
            try:
                await send_email_otp(user_id, username, invalidate_previous=False)
            except Exception as e:
                logger.warning("Failed to send email OTP to %s: %s", username[:3] + "***", e)
                await _write_audit(user_id, AuditAction.LOGIN_FAILURE, {"reason": "email_send_error"}, ip)
                return None
            return NEEDS_EMAIL_OTP
        # Verify the code
        from app.services.otp_service import verify_email_otp
        if not await verify_email_otp(user_id, totp_code):
            await _increment_failed_login(user_id, ip)
            return None

    # Full success — reset failed count
    await db.execute(
        "UPDATE users SET failed_login_count = 0, lockout_until = NULL WHERE id = ?",
        (user_id,),
    )
    await _write_audit(user_id, AuditAction.LOGIN_SUCCESS, None, ip)
    return row


async def _increment_failed_login(user_id: int, ip: Optional[str]) -> None:
    await db.execute(
        """
        UPDATE users
        SET failed_login_count = failed_login_count + 1,
            lockout_until = CASE
                WHEN failed_login_count + 1 >= ?
                THEN datetime('now', ? || ' minutes')
                ELSE lockout_until
            END
        WHERE id = ?
        """,
        (MAX_FAILED_ATTEMPTS, str(LOCKOUT_MINUTES), user_id),
    )
    row = await db.fetchone("SELECT failed_login_count FROM users WHERE id = ?", (user_id,))
    count = row["failed_login_count"] if row else 0
    if count >= MAX_FAILED_ATTEMPTS:
        await _write_audit(user_id, AuditAction.LOGIN_LOCKED, {"failed_attempts": count}, ip)
    else:
        await _write_audit(user_id, AuditAction.LOGIN_FAILURE, {"failed_attempts": count}, ip)
