"""Tests for email OTP generation, verification, replay, and expiry."""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from app.services import otp_service


def test_generate_otp_is_six_digits():
    for _ in range(50):
        code = otp_service._generate_otp()
        assert len(code) == otp_service.OTP_LENGTH
        assert code.isdigit()


class TestSendAndVerify:
    async def test_verify_success_consumes_code(self, setup_db, test_user):
        uid = test_user["id"]
        with patch("app.services.otp_service.send_otp_email"):
            captured = {}
            orig = otp_service._hash_otp
            # Capture the generated code by intercepting the hash step
            with patch("app.services.otp_service._generate_otp", return_value="123456"):
                await otp_service.send_email_otp(uid, "u@example.com")
        assert await otp_service.verify_email_otp(uid, "123456") is True
        # Second use of the same code fails (single-use)
        assert await otp_service.verify_email_otp(uid, "123456") is False

    async def test_wrong_code_fails(self, setup_db, test_user):
        uid = test_user["id"]
        with (
            patch("app.services.otp_service.send_otp_email"),
            patch("app.services.otp_service._generate_otp", return_value="111111"),
        ):
            await otp_service.send_email_otp(uid, "u@example.com")
        assert await otp_service.verify_email_otp(uid, "999999") is False
        # Correct code still works afterwards (wrong guess didn't consume it)
        assert await otp_service.verify_email_otp(uid, "111111") is True

    async def test_expired_code_rejected(self, setup_db, test_user):
        uid = test_user["id"]
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        await setup_db.execute(
            "INSERT INTO email_otp_codes (user_id, hashed_code, expires_at) VALUES (?, ?, ?)",
            (uid, otp_service._hash_otp("222222"), past),
        )
        assert await otp_service.verify_email_otp(uid, "222222") is False

    async def test_invalidate_previous_voids_old_codes(self, setup_db, test_user):
        uid = test_user["id"]
        with patch("app.services.otp_service.send_otp_email"):
            with patch("app.services.otp_service._generate_otp", return_value="333333"):
                await otp_service.send_email_otp(uid, "u@example.com")
            # invalidate_previous=True (default) marks the old code used
            with patch("app.services.otp_service._generate_otp", return_value="444444"):
                await otp_service.send_email_otp(uid, "u@example.com")
        assert await otp_service.verify_email_otp(uid, "333333") is False
        assert await otp_service.verify_email_otp(uid, "444444") is True

    async def test_login_flow_reuses_valid_code(self, setup_db, test_user):
        uid = test_user["id"]
        sent = []
        with patch("app.services.otp_service.send_otp_email", side_effect=lambda *a: sent.append(a)):
            with patch("app.services.otp_service._generate_otp", return_value="555555"):
                await otp_service.send_email_otp(uid, "u@example.com", invalidate_previous=False)
                # A second login-flow send should NOT dispatch a new email
                await otp_service.send_email_otp(uid, "u@example.com", invalidate_previous=False)
        assert len(sent) == 1

    async def test_cleanup_removes_expired(self, setup_db, test_user):
        uid = test_user["id"]
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        await setup_db.execute(
            "INSERT INTO email_otp_codes (user_id, hashed_code, expires_at) VALUES (?, ?, ?)",
            (uid, otp_service._hash_otp("000000"), old),
        )
        await otp_service.cleanup_expired_otps()
        row = await setup_db.fetchone(
            "SELECT COUNT(*) AS n FROM email_otp_codes WHERE user_id = ?", (uid,)
        )
        assert row["n"] == 0
