"""Best-effort security notification e-mails.

Every change to how an account can be signed into (password, e-mail, MFA
method, passkeys, recovery) tells the account owner about it. Notifications are
advisory: a failed SMTP send is logged and never blocks the change itself, and
nothing is sent at all when SMTP is not configured.
"""
import asyncio
import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.services.email_service import send_plain_email

logger = logging.getLogger(__name__)

_SUBJECTS = {
    "PASSWORD_CHANGED": "Nexus — your password was changed",
    "EMAIL_CHANGED": "Nexus — your account e-mail was changed",
    "MFA_METHOD_CHANGED": "Nexus — your sign-in verification method was changed",
    "TOTP_ENROLLED": "Nexus — an authenticator app was added to your account",
    "PASSKEY_ADDED": "Nexus — a passkey was added to your account",
    "PASSKEY_REMOVED": "Nexus — a passkey was removed from your account",
    "EMAIL_OTP_ENABLED": "Nexus — e-mail codes were enabled for sign-in",
    "EMAIL_OTP_DISABLED": "Nexus — e-mail codes were disabled for sign-in",
    "MFA_RESET_VIA_RECOVERY": "Nexus — your two-factor settings were reset",
    "ACCOUNT_DELETED": "Nexus — your account was deleted",
}


async def notify(to_address: str, event: str, detail: str = "", ip: str | None = None) -> None:
    s = get_settings()
    if not s.smtp_host or not to_address:
        return
    subject = _SUBJECTS.get(event, f"Nexus — security event: {event}")
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"{subject.split('— ', 1)[-1].capitalize()} on {when}.",
    ]
    if detail:
        lines.append(detail)
    if ip:
        lines.append(f"Request came from {ip}.")
    lines.append("")
    lines.append(
        "If this was you, no action is needed. If it was not, sign in from a trusted "
        "device and change your password immediately; that signs out every other session."
    )
    try:
        await asyncio.to_thread(send_plain_email, to_address, subject, "\n".join(lines))
    except Exception as exc:  # never let a notification failure break the action
        logger.warning("Security notification %s to %s*** failed: %s", event, to_address[:3], exc)
