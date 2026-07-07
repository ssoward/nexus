"""Router tests for passkey/WebAuthn endpoints.

These exercise the non-cryptographic paths: credential/password gating,
username-enumeration resistance, account lockout, unknown-credential handling,
and post-login credential management. The actual WebAuthn assertion crypto is
covered by the py-webauthn library and is not re-verified here.
"""
import pytest
from httpx import AsyncClient

from app.crypto import encrypt_totp_secret, hash_password


async def _seed_passkey(setup_db, user_id, credential_id=b"cred-abc"):
    return await setup_db.execute_returning(
        "INSERT INTO passkey_credentials (user_id, credential_id, public_key, sign_count, transports) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, credential_id, b"pubkey", 0, "[]"),
    )


class TestSetupBegin:
    async def test_unknown_user_401(self, client: AsyncClient, setup_db):
        r = await client.post(
            "/api/auth/passkey/setup/begin",
            json={"username": "ghost@example.com", "password": "whatever-123456!"},
        )
        assert r.status_code == 401

    async def test_wrong_password_401(self, client: AsyncClient, test_user):
        r = await client.post(
            "/api/auth/passkey/setup/begin",
            json={"username": test_user["username"], "password": "WrongPass123456!"},
        )
        assert r.status_code == 401

    async def test_already_configured_mfa_409(self, client: AsyncClient, setup_db, test_user):
        await setup_db.execute(
            "UPDATE users SET mfa_method = 'totp' WHERE id = ?", (test_user["id"],)
        )
        r = await client.post(
            "/api/auth/passkey/setup/begin",
            json={"username": test_user["username"], "password": test_user["password"]},
        )
        assert r.status_code == 409

    async def test_valid_credentials_returns_options(self, client: AsyncClient, test_user):
        r = await client.post(
            "/api/auth/passkey/setup/begin",
            json={"username": test_user["username"], "password": test_user["password"]},
        )
        assert r.status_code == 200
        assert "challenge" in r.json()


class TestAuthenticateBegin:
    async def test_unknown_user_and_no_passkey_are_identical(self, client: AsyncClient, test_user):
        # Unknown user
        r1 = await client.post(
            "/api/auth/passkey/authenticate/begin", json={"username": "ghost@example.com"}
        )
        # Known user with no passkeys
        r2 = await client.post(
            "/api/auth/passkey/authenticate/begin", json={"username": test_user["username"]}
        )
        assert r1.status_code == r2.status_code == 400
        assert r1.json()["detail"] == r2.json()["detail"]

    async def test_returns_options_when_passkey_present(self, client: AsyncClient, setup_db, test_user):
        await _seed_passkey(setup_db, test_user["id"])
        r = await client.post(
            "/api/auth/passkey/authenticate/begin", json={"username": test_user["username"]}
        )
        assert r.status_code == 200
        assert "challenge" in r.json()


class TestAuthenticateComplete:
    async def test_unknown_user_401(self, client: AsyncClient, setup_db):
        r = await client.post(
            "/api/auth/passkey/authenticate/complete",
            json={"username": "ghost@example.com", "credential": {"id": "x"}},
        )
        assert r.status_code == 401

    async def test_locked_account_401(self, client: AsyncClient, setup_db, test_user):
        await setup_db.execute(
            "UPDATE users SET lockout_until = datetime('now', '+15 minutes') WHERE id = ?",
            (test_user["id"],),
        )
        await _seed_passkey(setup_db, test_user["id"])
        r = await client.post(
            "/api/auth/passkey/authenticate/complete",
            json={"username": test_user["username"], "credential": {"id": "x"}},
        )
        assert r.status_code == 401


class TestPasswordlessComplete:
    async def test_unknown_credential_400(self, client: AsyncClient, setup_db):
        from webauthn.helpers import bytes_to_base64url
        # Need a pending challenge first
        begin = await client.post("/api/auth/passkey/login/begin")
        token = begin.json()["challenge_token"]
        r = await client.post(
            "/api/auth/passkey/login/complete",
            json={
                "credential": {"id": bytes_to_base64url(b"does-not-exist")},
                "challenge_token": token,
            },
        )
        assert r.status_code == 400

    async def test_login_begin_returns_challenge_token(self, client: AsyncClient, setup_db):
        r = await client.post("/api/auth/passkey/login/begin")
        assert r.status_code == 200
        assert "challenge_token" in r.json()


class TestCredentialManagement:
    async def test_list_requires_auth(self, client: AsyncClient, setup_db):
        assert (await client.get("/api/auth/passkey/credentials")).status_code == 401

    async def test_list_own_credentials(self, auth_client, setup_db):
        ac, user = auth_client
        await _seed_passkey(setup_db, user["id"])
        r = await ac.get("/api/auth/passkey/credentials")
        assert r.status_code == 200
        assert len(r.json()) == 1

    async def test_delete_last_credential_clears_mfa_method(self, auth_client, setup_db):
        ac, user = auth_client
        cred_id = await _seed_passkey(setup_db, user["id"])
        await setup_db.execute(
            "UPDATE users SET mfa_method = 'passkey' WHERE id = ?", (user["id"],)
        )
        r = await ac.delete(f"/api/auth/passkey/credentials/{cred_id}")
        assert r.status_code == 200
        row = await setup_db.fetchone(
            "SELECT mfa_method FROM users WHERE id = ?", (user["id"],)
        )
        assert row["mfa_method"] is None

    async def test_cannot_delete_another_users_credential(self, auth_client, setup_db):
        ac, _ = auth_client
        await setup_db.execute(
            "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
            ("pk-other@example.com", "x" * 60),
        )
        other = await setup_db.fetchone(
            "SELECT id FROM users WHERE username = ?", ("pk-other@example.com",)
        )
        cred_id = await _seed_passkey(setup_db, other["id"], credential_id=b"other-cred")
        r = await ac.delete(f"/api/auth/passkey/credentials/{cred_id}")
        assert r.status_code == 404
