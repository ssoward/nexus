"""Integration tests for auth endpoints and auth service logic."""
import pyotp
import pytest
from httpx import AsyncClient

from app.crypto import encrypt_totp_secret, hash_password
from app.database import db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _add_totp(username: str, password: str) -> tuple[int, str]:
    """Insert a user with a TOTP secret; return (user_id, raw_totp_secret)."""
    await db.execute(
        "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
        (username, hash_password(password)),
    )
    row = await db.fetchone("SELECT id FROM users WHERE username = ?", (username,))
    user_id = row["id"]
    secret = pyotp.random_base32()
    await db.execute(
        "UPDATE users SET encrypted_totp_secret = ?, mfa_method = 'totp' WHERE id = ?",
        (encrypt_totp_secret(secret, user_id), user_id),
    )
    return user_id, secret


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

class TestLogin:
    async def test_requires_totp_setup_when_none_configured(self, client: AsyncClient, test_user: dict):
        """Login must be blocked until an authenticator app is configured."""
        r = await client.post(
            "/api/auth/login",
            data={"username": test_user["username"], "password": test_user["password"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["needs_mfa_setup"] is True
        assert "access_token" not in r.cookies

    async def test_wrong_password(self, client: AsyncClient, test_user: dict):
        r = await client.post(
            "/api/auth/login",
            data={"username": test_user["username"], "password": "WrongPassword9!"},
        )
        assert r.status_code == 401

    async def test_unknown_user(self, client: AsyncClient, setup_db):
        r = await client.post(
            "/api/auth/login",
            data={"username": "nobody", "password": "DoesNotMatter1!"},
        )
        assert r.status_code == 401

    async def test_needs_totp_when_code_not_provided(self, client: AsyncClient, setup_db):
        await _add_totp("totpuser", "TestPassword1!Secure")
        r = await client.post(
            "/api/auth/login",
            data={"username": "totpuser", "password": "TestPassword1!Secure"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["needs_totp"] is True

    async def test_success_with_valid_totp(self, client: AsyncClient, setup_db):
        _, secret = await _add_totp("totpuser2", "TestPassword1!Secure")
        code = pyotp.TOTP(secret).now()
        r = await client.post(
            "/api/auth/login",
            data={
                "username": "totpuser2",
                "password": "TestPassword1!Secure",
                "totp_code": code,
            },
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_invalid_totp_code_rejected(self, client: AsyncClient, setup_db):
        await _add_totp("totpuser3", "TestPassword1!Secure")
        r = await client.post(
            "/api/auth/login",
            data={
                "username": "totpuser3",
                "password": "TestPassword1!Secure",
                "totp_code": "000000",
            },
        )
        assert r.status_code == 401

    async def test_account_locked_after_five_failures(
        self, client: AsyncClient, test_user: dict, setup_db
    ):
        """An account with an active lockout_until rejects valid credentials.

        We set the lock directly in the DB to avoid consuming rate-limit quota.
        """
        from datetime import datetime, timedelta, timezone

        lockout = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        await setup_db.execute(
            "UPDATE users SET failed_login_count = 5, lockout_until = ? WHERE id = ?",
            (lockout, test_user["id"]),
        )
        r = await client.post(
            "/api/auth/login",
            data={"username": test_user["username"], "password": test_user["password"]},
        )
        assert r.status_code == 401

    async def test_successful_login_resets_failed_count(
        self, client: AsyncClient, setup_db
    ):
        """A full successful login (with TOTP) resets failed_login_count to 0."""
        _, secret = await _add_totp("resetuser", "TestPassword1!Secure")
        row = await setup_db.fetchone(
            "SELECT id FROM users WHERE username = ?", ("resetuser",)
        )
        await setup_db.execute(
            "UPDATE users SET failed_login_count = 3 WHERE id = ?", (row["id"],)
        )
        code = pyotp.TOTP(secret).now()
        r = await client.post(
            "/api/auth/login",
            data={
                "username": "resetuser",
                "password": "TestPassword1!Secure",
                "totp_code": code,
            },
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
        updated = await setup_db.fetchone(
            "SELECT failed_login_count FROM users WHERE id = ?", (row["id"],)
        )
        assert updated["failed_login_count"] == 0


# ---------------------------------------------------------------------------
# POST /api/auth/logout
# ---------------------------------------------------------------------------

class TestLogout:
    async def test_success(self, auth_client):
        ac, _ = auth_client
        r = await ac.post("/api/auth/logout")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_unauthenticated_returns_401(self, client: AsyncClient, setup_db):
        r = await client.post("/api/auth/logout")
        assert r.status_code == 401

    async def test_token_recorded_in_revoked_table(self, auth_client, setup_db):
        ac, _ = auth_client
        await ac.post("/api/auth/logout")
        rows = await setup_db.fetchall("SELECT jti FROM revoked_tokens", ())
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------

class TestMe:
    async def test_returns_user_info(self, auth_client):
        ac, user = auth_client
        r = await ac.get("/api/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["username"] == user["username"]
        assert body["id"] == user["id"]

    async def test_unauthenticated_returns_401(self, client: AsyncClient, setup_db):
        r = await client.get("/api/auth/me")
        assert r.status_code == 401

    async def test_invalid_cookie_returns_401(self, client: AsyncClient, setup_db):
        r = await client.get(
            "/api/auth/me", cookies={"access_token": "not-a-real-token"}
        )
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/auth/create-user
# ---------------------------------------------------------------------------

class TestCreateUser:
    async def test_creates_first_user(self, client: AsyncClient, setup_db):
        r = await client.post(
            "/api/auth/create-user",
            json={"username": "newuser@example.com", "password": "SecurePass1!longEnough"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_disabled_after_first_user_exists(self, client: AsyncClient, test_user: dict):
        r = await client.post(
            "/api/auth/create-user",
            json={"username": "second@example.com", "password": "SecurePass1!longEnough"},
        )
        assert r.status_code == 403

    async def test_rejects_weak_password(self, client: AsyncClient, setup_db):
        r = await client.post(
            "/api/auth/create-user",
            json={"username": "newuser@example.com", "password": "short"},
        )
        assert r.status_code == 422

    async def test_rejects_short_username(self, client: AsyncClient, setup_db):
        r = await client.post(
            "/api/auth/create-user",
            json={"username": "ab", "password": "SecurePass1!longEnough"},
        )
        assert r.status_code == 422

    async def test_rejects_password_missing_uppercase(self, client: AsyncClient, setup_db):
        r = await client.post(
            "/api/auth/create-user",
            json={"username": "newuser@example.com", "password": "alllowercase1!enough"},
        )
        assert r.status_code == 422

    async def test_rejects_password_missing_digit(self, client: AsyncClient, setup_db):
        r = await client.post(
            "/api/auth/create-user",
            json={"username": "newuser@example.com", "password": "NoDigitsHereAtAll!long"},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/auth/bootstrap-totp
# ---------------------------------------------------------------------------

class TestBootstrapTotp:
    async def test_success_no_existing_totp(self, client: AsyncClient, test_user: dict):
        r = await client.post(
            "/api/auth/bootstrap-totp",
            data={"username": test_user["username"], "password": test_user["password"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert "provisioning_uri" in body
        assert "qr_code_base64" in body

    async def test_fails_if_totp_already_set(self, client: AsyncClient, setup_db):
        _, _ = await _add_totp("totpowner", "TestPassword1!Secure")
        r = await client.post(
            "/api/auth/bootstrap-totp",
            data={"username": "totpowner", "password": "TestPassword1!Secure"},
        )
        assert r.status_code == 401

    async def test_wrong_password_rejected(self, client: AsyncClient, test_user: dict):
        r = await client.post(
            "/api/auth/bootstrap-totp",
            data={"username": test_user["username"], "password": "WrongPassword9!"},
        )
        assert r.status_code == 401
