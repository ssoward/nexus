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

    async def test_locked_account_is_not_blocked_from_passkey_auth(
        self, client: AsyncClient, setup_db, test_user
    ):
        """Password lockout must not gate passkey assertions (H1).

        A passkey cannot be brute-forced, and it is the owner's way back in while
        someone is hammering the password endpoint. With the lock set, the request
        must proceed to challenge handling (400: no pending challenge) rather than
        being refused up front (401: account locked).
        """
        await setup_db.execute(
            "UPDATE users SET failed_login_count = 5, lockout_until = datetime('now', '+15 minutes') "
            "WHERE id = ?",
            (test_user["id"],),
        )
        await _seed_passkey(setup_db, test_user["id"])
        r = await client.post(
            "/api/auth/passkey/authenticate/complete",
            json={"username": test_user["username"], "credential": {"id": "x"}},
        )
        assert r.status_code == 400
        assert "challenge" in r.json()["detail"].lower()

    async def test_failed_assertion_does_not_feed_password_lockout(
        self, client: AsyncClient, setup_db, test_user
    ):
        """Junk assertions are audited but never increment failed_login_count."""
        from webauthn.helpers import bytes_to_base64url
        await _seed_passkey(setup_db, test_user["id"])
        await client.post(
            "/api/auth/passkey/authenticate/begin", json={"username": test_user["username"]}
        )
        r = await client.post(
            "/api/auth/passkey/authenticate/complete",
            json={
                "username": test_user["username"],
                "credential": {
                    "id": bytes_to_base64url(b"cred-abc"),
                    "rawId": bytes_to_base64url(b"cred-abc"),
                    "response": {
                        "clientDataJSON": bytes_to_base64url(b"{}"),
                        "authenticatorData": bytes_to_base64url(b"x"),
                        "signature": bytes_to_base64url(b"x"),
                    },
                },
            },
        )
        assert r.status_code == 400
        row = await setup_db.fetchone(
            "SELECT failed_login_count, lockout_until FROM users WHERE id = ?", (test_user["id"],)
        )
        assert row["failed_login_count"] == 0
        assert row["lockout_until"] is None


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

    async def test_delete_last_credential_refused_without_another_factor(self, auth_client, setup_db):
        """Removing the only second factor would leave a password-only account that
        anyone holding the password could re-enrol — refuse with 409."""
        ac, user = auth_client
        cred_id = await _seed_passkey(setup_db, user["id"])
        await setup_db.execute(
            "UPDATE users SET mfa_method = 'passkey' WHERE id = ?", (user["id"],)
        )
        r = await ac.delete(f"/api/auth/passkey/credentials/{cred_id}")
        assert r.status_code == 409
        row = await setup_db.fetchone(
            "SELECT mfa_method FROM users WHERE id = ?", (user["id"],)
        )
        assert row["mfa_method"] == "passkey"
        remaining = await setup_db.fetchone(
            "SELECT COUNT(*) AS n FROM passkey_credentials WHERE user_id = ?", (user["id"],)
        )
        assert remaining["n"] == 1

    async def test_delete_last_credential_falls_back_to_other_factor(self, auth_client, setup_db):
        ac, user = auth_client
        cred_id = await _seed_passkey(setup_db, user["id"])
        await setup_db.execute(
            "UPDATE users SET mfa_method = 'passkey', encrypted_totp_secret = ? WHERE id = ?",
            (encrypt_totp_secret("JBSWY3DPEHPK3PXP", user["id"]), user["id"]),
        )
        r = await ac.delete(f"/api/auth/passkey/credentials/{cred_id}")
        assert r.status_code == 200
        row = await setup_db.fetchone(
            "SELECT mfa_method FROM users WHERE id = ?", (user["id"],)
        )
        assert row["mfa_method"] == "totp"

    async def test_delete_requires_recent_step_up(self, client: AsyncClient, setup_db, test_user):
        """A session whose second factor was verified long ago gets 403 step_up_required."""
        from app.services.token_service import create_access_token
        import time
        cred_id = await _seed_passkey(setup_db, test_user["id"])
        stale = create_access_token(test_user["id"], mfa_time=time.time() - 3600)
        r = await client.delete(
            f"/api/auth/passkey/credentials/{cred_id}",
            cookies={"__Host-access_token": stale},
        )
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "step_up_required"
        assert "passkey" in r.json()["detail"]["methods"]

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
