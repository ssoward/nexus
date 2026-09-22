"""Step-up authentication (M1/M2/M6): account changes need a fresh second factor,
MFA switching only selects enrolled factors, and first-user registration is gated."""
import time

import pyotp
import pytest
from httpx import AsyncClient

from app.crypto import encrypt_totp_secret, hash_password
from app.services.token_service import create_access_token, decode_access_token

PW = "TestPassword1!Secure"
NEW_PW = "AnotherPassword2@Secure"
TOTP_SECRET = "JBSWY3DPEHPK3PXP"


async def _enrol_totp(setup_db, user_id: int) -> None:
    await setup_db.execute(
        "UPDATE users SET encrypted_totp_secret = ?, mfa_method = 'totp' WHERE id = ?",
        (encrypt_totp_secret(TOTP_SECRET, user_id), user_id),
    )


def _cookie(token: str) -> dict:
    return {"__Host-access_token": token}


class TestRequireRecentMfa:
    async def test_stale_session_gets_step_up_required(self, client: AsyncClient, setup_db, test_user):
        await _enrol_totp(setup_db, test_user["id"])
        stale = create_access_token(test_user["id"], mfa_time=time.time() - 3600)
        r = await client.post(
            "/api/auth/change-password",
            json={"current_password": PW, "new_password": NEW_PW},
            cookies=_cookie(stale),
        )
        assert r.status_code == 403
        body = r.json()["detail"]
        assert body["code"] == "step_up_required"
        assert body["methods"] == ["totp"]
        # Nothing changed.
        row = await setup_db.fetchone("SELECT hashed_password FROM users WHERE id = ?", (test_user["id"],))
        from app.crypto import verify_password
        assert verify_password(PW, row["hashed_password"])

    async def test_fresh_session_allowed(self, client: AsyncClient, setup_db, test_user):
        await _enrol_totp(setup_db, test_user["id"])
        fresh = create_access_token(test_user["id"])
        r = await client.post(
            "/api/auth/change-password",
            json={"current_password": PW, "new_password": NEW_PW},
            cookies=_cookie(fresh),
        )
        assert r.status_code == 200, r.text

    async def test_legacy_token_without_mfa_time_uses_auth_time(self, client: AsyncClient, setup_db, test_user):
        """Tokens minted before mfa_time existed: fall back to auth_time (stale → prompt)."""
        import jwt as pyjwt, uuid
        from datetime import datetime, timedelta, timezone
        from app.config import get_settings
        s = get_settings()
        now = datetime.now(timezone.utc)
        legacy = pyjwt.encode(
            {"sub": str(test_user["id"]), "iat": now, "exp": now + timedelta(hours=1),
             "jti": str(uuid.uuid4()), "auth_time": (now - timedelta(hours=2)).timestamp()},
            s.jwt_secret, algorithm=s.jwt_algorithm,
        )
        r = await client.patch(
            "/api/auth/change-email",
            json={"current_password": PW, "new_email": "new@example.com"},
            cookies=_cookie(legacy),
        )
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "step_up_required"

    @pytest.mark.parametrize("path,method,body", [
        ("/api/auth/change-email", "patch", {"current_password": PW, "new_email": "x@example.com"}),
        ("/api/auth/account", "delete", {"password": PW}),
        ("/api/auth/setup-totp", "post", None),
        ("/api/auth/passkey/register/begin", "post", None),
        ("/api/auth/email-otp/enable", "post", None),
        ("/api/auth/email-otp/disable", "post", None),
    ])
    async def test_all_sensitive_endpoints_are_gated(
        self, client: AsyncClient, setup_db, test_user, path, method, body
    ):
        stale = create_access_token(test_user["id"], mfa_time=time.time() - 3600)
        kwargs = {"cookies": _cookie(stale)}
        if body is not None:
            kwargs["json"] = body
        if method == "delete":
            r = await client.request("DELETE", path, json=body, cookies=_cookie(stale))
        else:
            r = await getattr(client, method)(path, **kwargs)
        assert r.status_code == 403, f"{path}: {r.status_code} {r.text}"
        assert r.json()["detail"]["code"] == "step_up_required"


class TestStepUpEndpoint:
    async def test_methods_lists_enrolled_factors(self, client: AsyncClient, setup_db, test_user):
        await _enrol_totp(setup_db, test_user["id"])
        r = await client.get("/api/auth/step-up/methods", cookies=_cookie(create_access_token(test_user["id"])))
        assert r.status_code == 200
        assert r.json()["methods"] == ["totp"]

    async def test_totp_step_up_reissues_cookie_and_unlocks_action(self, client: AsyncClient, setup_db, test_user):
        await _enrol_totp(setup_db, test_user["id"])
        original_auth_time = time.time() - 7200
        stale = create_access_token(test_user["id"], auth_time=original_auth_time, mfa_time=original_auth_time)

        r = await client.post(
            "/api/auth/step-up",
            json={"method": "totp", "code": pyotp.TOTP(TOTP_SECRET).now()},
            cookies=_cookie(stale),
        )
        assert r.status_code == 200, r.text
        new_cookie = r.cookies.get("__Host-access_token")
        assert new_cookie
        payload = decode_access_token(new_cookie)
        # Original login preserved; second-factor timestamp refreshed.
        assert abs(payload["auth_time"] - original_auth_time) < 1
        assert time.time() - payload["mfa_time"] < 5

        r = await client.post(
            "/api/auth/change-password",
            json={"current_password": PW, "new_password": NEW_PW},
            cookies=_cookie(new_cookie),
        )
        assert r.status_code == 200, r.text
        audit = await setup_db.fetchall(
            "SELECT action FROM audit_log WHERE user_id = ? ORDER BY id", (test_user["id"],)
        )
        assert "STEP_UP_SUCCESS" in [a["action"] for a in audit]

    async def test_wrong_totp_fails_and_counts_toward_lockout(self, client: AsyncClient, setup_db, test_user):
        await _enrol_totp(setup_db, test_user["id"])
        r = await client.post(
            "/api/auth/step-up",
            json={"method": "totp", "code": "000000"},
            cookies=_cookie(create_access_token(test_user["id"])),
        )
        assert r.status_code == 401
        row = await setup_db.fetchone("SELECT failed_login_count FROM users WHERE id = ?", (test_user["id"],))
        assert row["failed_login_count"] == 1

    async def test_unenrolled_method_rejected(self, client: AsyncClient, setup_db, test_user):
        await _enrol_totp(setup_db, test_user["id"])
        r = await client.post(
            "/api/auth/step-up",
            json={"method": "email_otp", "code": "123456"},
            cookies=_cookie(create_access_token(test_user["id"])),
        )
        assert r.status_code == 400

    async def test_step_up_requires_session(self, client: AsyncClient, setup_db):
        r = await client.post("/api/auth/step-up", json={"method": "totp", "code": "1"})
        assert r.status_code == 401


class TestSwitchMfaEnrolmentOnly:
    async def test_switch_to_email_refused_when_not_enrolled(self, client: AsyncClient, setup_db):
        """Password-only callers cannot move a passkey account onto e-mail codes (M2)."""
        await setup_db.execute(
            "INSERT INTO users (username, hashed_password, mfa_method) VALUES (?, ?, 'passkey')",
            ("pk@example.com", hash_password(PW)),
        )
        r = await client.post(
            "/api/auth/switch-mfa",
            data={"username": "pk@example.com", "password": PW, "method": "email_otp"},
        )
        assert r.status_code == 409
        row = await setup_db.fetchone("SELECT mfa_method FROM users WHERE username = ?", ("pk@example.com",))
        assert row["mfa_method"] == "passkey"

    async def test_switch_to_enrolled_totp_is_audited(self, client: AsyncClient, setup_db):
        await setup_db.execute(
            "INSERT INTO users (username, hashed_password, mfa_method, email_otp_enrolled) "
            "VALUES (?, ?, 'email_otp', 1)",
            ("both@example.com", hash_password(PW)),
        )
        row = await setup_db.fetchone("SELECT id FROM users WHERE username = ?", ("both@example.com",))
        await setup_db.execute(
            "UPDATE users SET encrypted_totp_secret = ? WHERE id = ?",
            (encrypt_totp_secret(TOTP_SECRET, row["id"]), row["id"]),
        )
        r = await client.post(
            "/api/auth/switch-mfa",
            data={"username": "both@example.com", "password": PW, "method": "totp"},
        )
        assert r.status_code == 200
        audit = await setup_db.fetchone(
            "SELECT action, detail FROM audit_log WHERE user_id = ? AND action = 'MFA_METHOD_CHANGED'",
            (row["id"],),
        )
        assert audit is not None
        assert '"from": "email_otp"' in audit["detail"]

    async def test_login_available_methods_reflects_enrolment(self, client: AsyncClient, setup_db):
        """An account whose default is TOTP does not advertise e-mail unless enrolled."""
        await setup_db.execute(
            "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
            ("t@example.com", hash_password(PW)),
        )
        row = await setup_db.fetchone("SELECT id FROM users WHERE username = ?", ("t@example.com",))
        await _enrol_totp(setup_db, row["id"])
        r = await client.post("/api/auth/login", data={"username": "t@example.com", "password": PW})
        assert r.status_code == 200
        assert r.json()["available_methods"] == ["totp"]


class TestEmailOtpToggle:
    async def test_disable_refused_when_it_is_the_only_factor(self, client: AsyncClient, setup_db, test_user):
        await setup_db.execute(
            "UPDATE users SET mfa_method = 'email_otp', email_otp_enrolled = 1 WHERE id = ?",
            (test_user["id"],),
        )
        r = await client.post("/api/auth/email-otp/disable", cookies=_cookie(create_access_token(test_user["id"])))
        assert r.status_code == 409

    async def test_disable_falls_back_to_totp_default(self, client: AsyncClient, setup_db, test_user):
        await _enrol_totp(setup_db, test_user["id"])
        await setup_db.execute(
            "UPDATE users SET mfa_method = 'email_otp', email_otp_enrolled = 1 WHERE id = ?",
            (test_user["id"],),
        )
        r = await client.post("/api/auth/email-otp/disable", cookies=_cookie(create_access_token(test_user["id"])))
        assert r.status_code == 200
        row = await setup_db.fetchone(
            "SELECT mfa_method, email_otp_enrolled FROM users WHERE id = ?", (test_user["id"],)
        )
        assert row["mfa_method"] == "totp"
        assert row["email_otp_enrolled"] == 0


class TestFirstUserGate:
    async def test_setup_token_required_when_configured(self, client: AsyncClient, setup_db, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "nexus_setup_token", "letmein-setup-token")
        body = {"username": "owner@example.com", "password": PW}
        r = await client.post("/api/auth/create-user", json=body)
        assert r.status_code == 403
        r = await client.post("/api/auth/create-user", json={**body, "setup_token": "wrong"})
        assert r.status_code == 403
        r = await client.post("/api/auth/create-user", json={**body, "setup_token": "letmein-setup-token"})
        assert r.status_code == 200, r.text
        monkeypatch.setattr(get_settings(), "nexus_setup_token", "")

    async def test_concurrent_first_registrations_yield_one_owner(self, client: AsyncClient, setup_db):
        import asyncio
        body = lambda i: {"username": f"owner{i}@example.com", "password": PW}
        results = await asyncio.gather(*[client.post("/api/auth/create-user", json=body(i)) for i in range(5)])
        codes = sorted(r.status_code for r in results)
        assert codes.count(200) == 1
        assert all(c in (200, 403) for c in codes)
        count = await setup_db.fetchone("SELECT COUNT(*) AS n FROM users")
        assert count["n"] == 1
