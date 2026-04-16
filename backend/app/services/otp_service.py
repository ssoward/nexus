"""Generate, store, verify, and clean up email OTP codes."""

import asyncio
import logging
import secrets
from datetime import datetime, timezone, timedelta

import bcrypt

from app.database import db
from app.services.email_service import send_otp_email

logger = logging.getLogger(__name__)

OTP_TTL_MINUTES = 10
OTP_LENGTH = 6


def _generate_otp() -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(OTP_LENGTH))


def _hash_otp(code: str) -> str:
    return bcrypt.hashpw(code.encode(), bcrypt.gensalt(rounds=12)).decode()


def _verify_otp_hash(code: str, hashed: str) -> bool:
    return bcrypt.checkpw(code.encode(), hashed.encode())


async def send_email_otp(user_id: int, email: str, invalidate_previous: bool = True) -> None:
    """Generate code, store bcrypt hash, send email.

    invalidate_previous=True (default): used by resend/setup — old codes voided.
    invalidate_previous=False: used by login flow — keeps existing valid code
    so retries don't break the first code sent.
    """
    if not invalidate_previous:
        # Check if there's already a valid, unused code — skip sending if so
        existing = await db.fetchone(
            "SELECT id FROM email_otp_codes WHERE user_id = ? AND used = 0 AND expires_at > ?",
            (user_id, datetime.now(timezone.utc).isoformat()),
        )
        if existing:
            return  # valid code already pending, don't spam

    if invalidate_previous:
        await db.execute(
            "UPDATE email_otp_codes SET used = 1 WHERE user_id = ? AND used = 0",
            (user_id,),
        )

    code = _generate_otp()
    hashed = _hash_otp(code)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)).isoformat()

    await db.execute(
        "INSERT INTO email_otp_codes (user_id, hashed_code, expires_at) VALUES (?, ?, ?)",
        (user_id, hashed, expires_at),
    )

    await asyncio.to_thread(send_otp_email, email, code)


async def verify_email_otp(user_id: int, code: str) -> bool:
    """Verify a code against the most recent unused codes. Consumes on success."""
    rows = await db.fetchall(
        "SELECT id, hashed_code, expires_at FROM email_otp_codes "
        "WHERE user_id = ? AND used = 0 ORDER BY created_at DESC LIMIT 5",
        (user_id,),
    )
    now = datetime.now(timezone.utc)
    for row in rows:
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            continue
        if _verify_otp_hash(code, row["hashed_code"]):
            await db.execute("UPDATE email_otp_codes SET used = 1 WHERE id = ?", (row["id"],))
            return True
    return False


async def cleanup_expired_otps() -> None:
    """Delete expired codes. Called periodically from watchdog."""
    await db.execute(
        "DELETE FROM email_otp_codes WHERE expires_at < datetime('now', '-1 hour')",
    )
