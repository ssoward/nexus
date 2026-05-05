import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

import webauthn
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorAssertionResponse,
    AuthenticatorAttestationResponse,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    AuthenticationCredential,
    PublicKeyCredentialDescriptor,
    RegistrationCredential,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import get_settings
from app.crypto import verify_password
from app.database import db
from app.dependencies import get_current_user
from app.limiter import limiter
from app.models.audit import AuditAction
from app.services.token_service import create_access_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth/passkey", tags=["passkey"])

CHALLENGE_TTL_SECONDS = 120
COOKIE_NAME = "access_token"


def _set_auth_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=s.jwt_expire_minutes * 60,
        path="/",
    )


def _get_origin(request: Request) -> str:  # noqa: ARG001
    s = get_settings()
    if s.webauthn_origin:
        return s.webauthn_origin
    return f"https://{s.rp_id}"


async def _store_challenge(user_id: int, challenge_bytes: bytes, purpose: str) -> None:
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=CHALLENGE_TTL_SECONDS)).isoformat()
    await db.execute(
        "INSERT INTO webauthn_challenges (user_id, challenge, purpose, expires_at) VALUES (?, ?, ?, ?)",
        (user_id, bytes_to_base64url(challenge_bytes), purpose, expires_at),
    )


async def _consume_challenge(user_id: int, purpose: str) -> bytes:
    row = await db.fetchone(
        "SELECT id, challenge, expires_at FROM webauthn_challenges "
        "WHERE user_id = ? AND purpose = ? AND used = 0 ORDER BY id DESC LIMIT 1",
        (user_id, purpose),
    )
    if not row:
        raise HTTPException(status_code=400, detail="No pending challenge. Restart the process.")
    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Challenge expired. Restart the process.")
    await db.execute("UPDATE webauthn_challenges SET used = 1 WHERE id = ?", (row["id"],))
    return base64url_to_bytes(row["challenge"])


def _parse_transports(raw: list) -> list[AuthenticatorTransport]:
    result = []
    for t in raw:
        try:
            result.append(AuthenticatorTransport(t))
        except ValueError:
            pass
    return result


def _build_registration_credential(data: dict) -> RegistrationCredential:
    resp = data.get("response", {})
    return RegistrationCredential(
        id=data["id"],
        raw_id=base64url_to_bytes(data["rawId"]),
        response=AuthenticatorAttestationResponse(
            client_data_json=base64url_to_bytes(resp["clientDataJSON"]),
            attestation_object=base64url_to_bytes(resp["attestationObject"]),
            transports=_parse_transports(resp.get("transports", [])) or None,
        ),
        type=data.get("type", "public-key"),
    )


def _build_authentication_credential(data: dict) -> AuthenticationCredential:
    resp = data.get("response", {})
    return AuthenticationCredential(
        id=data["id"],
        raw_id=base64url_to_bytes(data["rawId"]),
        response=AuthenticatorAssertionResponse(
            client_data_json=base64url_to_bytes(resp["clientDataJSON"]),
            authenticator_data=base64url_to_bytes(resp["authenticatorData"]),
            signature=base64url_to_bytes(resp["signature"]),
            user_handle=base64url_to_bytes(resp["userHandle"]) if resp.get("userHandle") else None,
        ),
        type=data.get("type", "public-key"),
    )


# ── First-time MFA setup (no session required) ───────────────────────────────

class SetupBeginRequest(BaseModel):
    username: str
    password: str


@router.post("/setup/begin")
@limiter.limit("5/minute")
async def setup_begin(request: Request, req: SetupBeginRequest):
    """Begin passkey registration for first-time MFA setup. Verifies credentials before issuing options."""
    row = await db.fetchone(
        "SELECT id, hashed_password, mfa_method FROM users WHERE username = ?",
        (req.username,),
    )
    if not row or not verify_password(req.password, row["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if row["mfa_method"] is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA already configured")

    s = get_settings()
    options = webauthn.generate_registration_options(
        rp_id=s.rp_id,
        rp_name=s.rp_name,
        user_id=str(row["id"]).encode(),
        user_name=req.username,
        user_display_name=req.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    await _store_challenge(row["id"], options.challenge, "register")
    return json.loads(webauthn.options_to_json(options))


class SetupCompleteRequest(BaseModel):
    username: str
    password: str
    credential: dict


@router.post("/setup/complete")
@limiter.limit("5/minute")
async def setup_complete(request: Request, response: Response, req: SetupCompleteRequest):
    """Complete first-time passkey registration, then issue an auth cookie."""
    row = await db.fetchone(
        "SELECT id, hashed_password FROM users WHERE username = ?",
        (req.username,),
    )
    if not row or not verify_password(req.password, row["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    expected_challenge = await _consume_challenge(row["id"], "register")
    s = get_settings()

    try:
        cred = _build_registration_credential(req.credential)
        verified = webauthn.verify_registration_response(
            credential=cred,
            expected_challenge=expected_challenge,
            expected_rp_id=s.rp_id,
            expected_origin=_get_origin(request),
            require_user_verification=True,
        )
    except Exception as exc:
        logger.warning("Passkey setup_complete failed for user %s: %s", row["id"], exc)
        raise HTTPException(status_code=400, detail="Passkey verification failed. Try again.")

    transports = json.dumps(req.credential.get("response", {}).get("transports", []))
    await db.execute(
        "INSERT INTO passkey_credentials (user_id, credential_id, public_key, sign_count, transports, aaguid) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            row["id"],
            verified.credential_id,
            verified.credential_public_key,
            verified.sign_count,
            transports,
            str(verified.aaguid) if verified.aaguid else None,
        ),
    )
    await db.execute("UPDATE users SET mfa_method = 'passkey' WHERE id = ?", (row["id"],))
    await db.execute(
        "INSERT INTO audit_log (user_id, action, ip_address) VALUES (?, ?, ?)",
        (row["id"], AuditAction.PASSKEY_REGISTER.value, request.client.host if request.client else None),
    )

    token = create_access_token(row["id"])
    _set_auth_cookie(response, token)
    return {"ok": True, "username": req.username}


# ── Login assertion (no session required) ────────────────────────────────────

class AuthBeginRequest(BaseModel):
    username: str


@router.post("/authenticate/begin")
@limiter.limit("10/minute")
async def authenticate_begin(request: Request, req: AuthBeginRequest):
    """Return assertion options for a user with registered passkeys."""
    row = await db.fetchone("SELECT id FROM users WHERE username = ?", (req.username,))
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    creds = await db.fetchall(
        "SELECT credential_id, transports FROM passkey_credentials WHERE user_id = ?",
        (row["id"],),
    )
    if not creds:
        raise HTTPException(status_code=400, detail="No passkeys registered for this account")

    s = get_settings()
    allow_credentials = [
        PublicKeyCredentialDescriptor(
            id=bytes(c["credential_id"]),
            transports=_parse_transports(json.loads(c["transports"] or "[]")) or None,
        )
        for c in creds
    ]
    options = webauthn.generate_authentication_options(
        rp_id=s.rp_id,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    await _store_challenge(row["id"], options.challenge, "authenticate")
    return json.loads(webauthn.options_to_json(options))


class AuthCompleteRequest(BaseModel):
    username: str
    credential: dict


@router.post("/authenticate/complete")
@limiter.limit("10/minute")
async def authenticate_complete(request: Request, response: Response, req: AuthCompleteRequest):
    """Verify assertion and issue auth cookie on success."""
    row = await db.fetchone(
        "SELECT id, username, failed_login_count, lockout_until FROM users WHERE username = ?",
        (req.username,),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if row["lockout_until"]:
        lockout_until = datetime.fromisoformat(row["lockout_until"])
        if lockout_until.tzinfo is None:
            lockout_until = lockout_until.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < lockout_until:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account locked")

    expected_challenge = await _consume_challenge(row["id"], "authenticate")
    s = get_settings()

    cred_id_bytes = base64url_to_bytes(req.credential["id"])
    cred_row = await db.fetchone(
        "SELECT id, public_key, sign_count FROM passkey_credentials WHERE user_id = ? AND credential_id = ?",
        (row["id"], cred_id_bytes),
    )
    if not cred_row:
        raise HTTPException(status_code=400, detail="Unknown credential")

    try:
        cred = _build_authentication_credential(req.credential)
        verified = webauthn.verify_authentication_response(
            credential=cred,
            expected_challenge=expected_challenge,
            expected_rp_id=s.rp_id,
            expected_origin=_get_origin(request),
            credential_public_key=bytes(cred_row["public_key"]),
            credential_current_sign_count=cred_row["sign_count"],
            require_user_verification=True,
        )
    except Exception as exc:
        logger.warning("Passkey authenticate_complete failed for user %s: %s", row["id"], exc)
        await db.execute(
            "UPDATE users SET failed_login_count = failed_login_count + 1 WHERE id = ?",
            (row["id"],),
        )
        await db.execute(
            "INSERT INTO audit_log (user_id, action, ip_address) VALUES (?, ?, ?)",
            (row["id"], AuditAction.PASSKEY_AUTH_FAILURE.value, request.client.host if request.client else None),
        )
        raise HTTPException(status_code=400, detail="Passkey verification failed")

    await db.execute(
        "UPDATE passkey_credentials SET sign_count = ?, last_used_at = ? WHERE id = ?",
        (verified.new_sign_count, datetime.now(timezone.utc).isoformat(), cred_row["id"]),
    )
    await db.execute(
        "UPDATE users SET failed_login_count = 0, lockout_until = NULL WHERE id = ?",
        (row["id"],),
    )
    await db.execute(
        "INSERT INTO audit_log (user_id, action, ip_address) VALUES (?, ?, ?)",
        (row["id"], AuditAction.PASSKEY_AUTH_SUCCESS.value, request.client.host if request.client else None),
    )

    token = create_access_token(row["id"])
    _set_auth_cookie(response, token)
    return {"ok": True, "username": req.username}


# ── Post-login credential management (session required) ──────────────────────

@router.post("/register/begin")
@limiter.limit("5/minute")
async def register_begin(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Begin passkey registration for an already-authenticated user."""
    s = get_settings()
    options = webauthn.generate_registration_options(
        rp_id=s.rp_id,
        rp_name=s.rp_name,
        user_id=str(current_user["id"]).encode(),
        user_name=current_user["username"],
        user_display_name=current_user["username"],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    await _store_challenge(current_user["id"], options.challenge, "register")
    return json.loads(webauthn.options_to_json(options))


class RegisterCompleteRequest(BaseModel):
    credential: dict
    name: str = ""


@router.post("/register/complete")
@limiter.limit("5/minute")
async def register_complete(
    request: Request,
    req: RegisterCompleteRequest,
    current_user: dict = Depends(get_current_user),
):
    """Complete passkey registration for an already-authenticated user."""
    expected_challenge = await _consume_challenge(current_user["id"], "register")
    s = get_settings()

    try:
        cred = _build_registration_credential(req.credential)
        verified = webauthn.verify_registration_response(
            credential=cred,
            expected_challenge=expected_challenge,
            expected_rp_id=s.rp_id,
            expected_origin=_get_origin(request),
            require_user_verification=True,
        )
    except Exception as exc:
        logger.warning("Passkey register_complete failed for user %s: %s", current_user["id"], exc)
        raise HTTPException(status_code=400, detail="Passkey verification failed. Try again.")

    transports = json.dumps(req.credential.get("response", {}).get("transports", []))
    await db.execute(
        "INSERT INTO passkey_credentials (user_id, credential_id, public_key, sign_count, transports, aaguid, name) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            current_user["id"],
            verified.credential_id,
            verified.credential_public_key,
            verified.sign_count,
            transports,
            str(verified.aaguid) if verified.aaguid else None,
            req.name or None,
        ),
    )
    await db.execute("UPDATE users SET mfa_method = 'passkey' WHERE id = ?", (current_user["id"],))
    await db.execute(
        "INSERT INTO audit_log (user_id, action, ip_address) VALUES (?, ?, ?)",
        (current_user["id"], AuditAction.PASSKEY_REGISTER.value, request.client.host if request.client else None),
    )
    return {"ok": True}


@router.get("/credentials")
async def list_credentials(current_user: dict = Depends(get_current_user)):
    rows = await db.fetchall(
        "SELECT id, name, aaguid, created_at, last_used_at FROM passkey_credentials "
        "WHERE user_id = ? ORDER BY created_at ASC",
        (current_user["id"],),
    )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "aaguid": row["aaguid"],
            "created_at": row["created_at"],
            "last_used_at": row["last_used_at"],
        }
        for row in rows
    ]


@router.delete("/credentials/{cred_id}")
async def delete_credential(
    request: Request,
    cred_id: int,
    current_user: dict = Depends(get_current_user),
):
    row = await db.fetchone(
        "SELECT id FROM passkey_credentials WHERE id = ? AND user_id = ?",
        (cred_id, current_user["id"]),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")

    await db.execute("DELETE FROM passkey_credentials WHERE id = ?", (cred_id,))
    await db.execute(
        "INSERT INTO audit_log (user_id, action, ip_address) VALUES (?, ?, ?)",
        (current_user["id"], AuditAction.PASSKEY_DELETE.value, request.client.host if request.client else None),
    )

    remaining = await db.fetchone(
        "SELECT COUNT(*) AS n FROM passkey_credentials WHERE user_id = ?",
        (current_user["id"],),
    )
    if remaining and remaining["n"] == 0:
        await db.execute("UPDATE users SET mfa_method = NULL WHERE id = ?", (current_user["id"],))

    return {"ok": True}


# ── Passwordless / biometric login (no username or password required) ─────────
#
# Uses WebAuthn discoverable credentials (resident keys).  The authenticator
# presents any passkey stored for this rp_id; the server identifies the user
# from the credential_id returned in the assertion.
#
# Challenge is stored with user_id=0 (anonymous sentinel — webauthn_challenges
# has no FK constraint so this is safe) keyed by a per-request UUID token that
# the frontend echoes back in the complete call.

async def _store_passwordless_challenge(challenge_bytes: bytes, token: str) -> None:
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=CHALLENGE_TTL_SECONDS)).isoformat()
    await db.execute(
        "INSERT INTO webauthn_challenges (user_id, challenge, purpose, expires_at) VALUES (?, ?, ?, ?)",
        (0, bytes_to_base64url(challenge_bytes), f"passwordless:{token}", expires_at),
    )


async def _consume_passwordless_challenge(token: str) -> bytes:
    row = await db.fetchone(
        "SELECT id, challenge, expires_at FROM webauthn_challenges "
        "WHERE user_id = 0 AND purpose = ? AND used = 0 ORDER BY id DESC LIMIT 1",
        (f"passwordless:{token}",),
    )
    if not row:
        raise HTTPException(status_code=400, detail="No pending challenge. Restart the sign-in.")
    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Challenge expired. Try again.")
    await db.execute("UPDATE webauthn_challenges SET used = 1 WHERE id = ?", (row["id"],))
    return base64url_to_bytes(row["challenge"])


@router.post("/login/begin")
@limiter.limit("10/minute")
async def login_begin_passwordless(request: Request):
    """Begin passwordless biometric login — no username or password required.

    Returns WebAuthn assertion options with an empty allow_credentials list so
    the platform authenticator can present any resident passkey stored for this
    rp_id.  The response also includes a challenge_token that must be echoed
    back to /login/complete to correlate the challenge.
    """
    s = get_settings()
    options = webauthn.generate_authentication_options(
        rp_id=s.rp_id,
        allow_credentials=[],  # discoverable — browser shows stored passkeys
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    token = str(uuid.uuid4())
    await _store_passwordless_challenge(options.challenge, token)
    response_data = json.loads(webauthn.options_to_json(options))
    response_data["challenge_token"] = token
    return response_data


class PasswordlessCompleteRequest(BaseModel):
    credential: dict
    challenge_token: str


@router.post("/login/complete")
@limiter.limit("10/minute")
async def login_complete_passwordless(
    request: Request,
    response: Response,
    req: PasswordlessCompleteRequest,
):
    """Verify passwordless assertion and issue auth cookie.

    The user is identified by matching the credential_id in the assertion
    against the passkey_credentials table — no username field needed.
    """
    expected_challenge = await _consume_passwordless_challenge(req.challenge_token)
    s = get_settings()

    cred_id_bytes = base64url_to_bytes(req.credential["id"])
    cred_row = await db.fetchone(
        "SELECT id, user_id, public_key, sign_count FROM passkey_credentials WHERE credential_id = ?",
        (cred_id_bytes,),
    )
    if not cred_row:
        raise HTTPException(status_code=400, detail="Unknown credential")

    user_row = await db.fetchone(
        "SELECT id, username, failed_login_count, lockout_until FROM users WHERE id = ?",
        (cred_row["user_id"],),
    )
    if not user_row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user_row["lockout_until"]:
        lockout_until = datetime.fromisoformat(user_row["lockout_until"])
        if lockout_until.tzinfo is None:
            lockout_until = lockout_until.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < lockout_until:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account locked")

    try:
        cred = _build_authentication_credential(req.credential)
        verified = webauthn.verify_authentication_response(
            credential=cred,
            expected_challenge=expected_challenge,
            expected_rp_id=s.rp_id,
            expected_origin=_get_origin(request),
            credential_public_key=bytes(cred_row["public_key"]),
            credential_current_sign_count=cred_row["sign_count"],
        )
    except Exception as exc:
        logger.warning("Passwordless login failed for user %s: %s", user_row["id"], exc)
        await db.execute(
            "UPDATE users SET failed_login_count = failed_login_count + 1 WHERE id = ?",
            (user_row["id"],),
        )
        await db.execute(
            "INSERT INTO audit_log (user_id, action, ip_address) VALUES (?, ?, ?)",
            (user_row["id"], AuditAction.PASSKEY_AUTH_FAILURE.value,
             request.client.host if request.client else None),
        )
        raise HTTPException(status_code=400, detail="Passkey verification failed")

    await db.execute(
        "UPDATE passkey_credentials SET sign_count = ?, last_used_at = ? WHERE id = ?",
        (verified.new_sign_count, datetime.now(timezone.utc).isoformat(), cred_row["id"]),
    )
    await db.execute(
        "UPDATE users SET failed_login_count = 0, lockout_until = NULL WHERE id = ?",
        (user_row["id"],),
    )
    await db.execute(
        "INSERT INTO audit_log (user_id, action, ip_address) VALUES (?, ?, ?)",
        (user_row["id"], AuditAction.PASSKEY_AUTH_SUCCESS.value,
         request.client.host if request.client else None),
    )

    token = create_access_token(user_row["id"])
    _set_auth_cookie(response, token)
    return {"ok": True, "username": user_row["username"]}
