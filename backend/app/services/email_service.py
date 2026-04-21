"""Send OTP codes via SMTP (Python smtplib, no third-party SDK)."""

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)


def send_otp_email(to_address: str, code: str) -> None:
    """Send a 6-digit OTP code. Raises on failure."""
    s = get_settings()
    if not s.smtp_host:
        raise RuntimeError("SMTP not configured — set SMTP_HOST/SMTP_USER/SMTP_PASSWORD/SMTP_FROM in .env")

    msg = EmailMessage()
    msg["Subject"] = f"Nexus sign-in code: {code}"
    msg["From"] = s.smtp_from
    msg["To"] = to_address
    msg.set_content(
        f"Your Nexus verification code is: {code}\n\n"
        f"This code expires in 10 minutes.\n"
        f"If you did not request this, ignore this email."
    )

    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as server:
        server.ehlo()
        if s.smtp_port != 25:
            server.starttls()
            server.ehlo()
        server.login(s.smtp_user, s.smtp_password)
        server.send_message(msg)

    logger.info("OTP email sent to %s", to_address[:3] + "***")


def send_recovery_email(to_address: str, recovery_url: str) -> None:
    """Send an MFA recovery link. Raises on failure."""
    s = get_settings()
    if not s.smtp_host:
        raise RuntimeError("SMTP not configured — set SMTP_HOST/SMTP_USER/SMTP_PASSWORD/SMTP_FROM in .env")

    msg = EmailMessage()
    msg["Subject"] = "Nexus — reset your MFA"
    msg["From"] = s.smtp_from
    msg["To"] = to_address
    msg.set_content(
        f"Someone requested an MFA reset for your Nexus account.\n\n"
        f"Click the link below to clear your current MFA method and choose a new one on next login.\n"
        f"This link expires in 15 minutes and can only be used once.\n\n"
        f"{recovery_url}\n\n"
        f"If you did not request this, ignore this email — your account is unchanged."
    )

    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as server:
        server.ehlo()
        if s.smtp_port != 25:
            server.starttls()
            server.ehlo()
        server.login(s.smtp_user, s.smtp_password)
        server.send_message(msg)

    logger.info("Recovery email sent to %s", to_address[:3] + "***")
