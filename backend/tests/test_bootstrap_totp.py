"""Tests for /api/auth/bootstrap-totp, including the I1 mfa_method fix."""
import pytest
from httpx import AsyncClient

from app.crypto import encrypt_totp_secret


class TestBootstrapTotp:
    async def test_unknown_user_401(self, client: AsyncClient, setup_db):
        r = await client.post(
            "/api/auth/bootstrap-totp",
            data={"username": "ghost@example.com", "password": "Whatever123456!!"},
        )
        assert r.status_code == 401

    async def test_wrong_password_401(self, client: AsyncClient, test_user):
        r = await client.post(
            "/api/auth/bootstrap-totp",
            data={"username": test_user["username"], "password": "WrongPassword123!!"},
        )
        assert r.status_code == 401

    async def test_success_sets_secret_and_mfa_method(self, client: AsyncClient, setup_db, test_user):
        r = await client.post(
            "/api/auth/bootstrap-totp",
            data={"username": test_user["username"], "password": test_user["password"]},
        )
        assert r.status_code == 200
        assert "provisioning_uri" in r.json()

        row = await setup_db.fetchone(
            "SELECT encrypted_totp_secret, mfa_method FROM users WHERE id = ?",
            (test_user["id"],),
        )
        assert row["encrypted_totp_secret"] is not None
        # I1: mfa_method must be set so the next login isn't stuck at NEEDS_MFA_SETUP
        assert row["mfa_method"] == "totp"

    async def test_refuses_when_totp_already_present(self, client: AsyncClient, setup_db, test_user):
        await setup_db.execute(
            "UPDATE users SET encrypted_totp_secret = ? WHERE id = ?",
            (encrypt_totp_secret("JBSWY3DPEHPK3PXP", test_user["id"]), test_user["id"]),
        )
        r = await client.post(
            "/api/auth/bootstrap-totp",
            data={"username": test_user["username"], "password": test_user["password"]},
        )
        assert r.status_code == 401

    async def test_refuses_when_mfa_method_already_set(self, client: AsyncClient, setup_db, test_user):
        await setup_db.execute(
            "UPDATE users SET mfa_method = 'passkey' WHERE id = ?", (test_user["id"],)
        )
        r = await client.post(
            "/api/auth/bootstrap-totp",
            data={"username": test_user["username"], "password": test_user["password"]},
        )
        assert r.status_code == 401
