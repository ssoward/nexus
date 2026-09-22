"""Step-up authentication: re-verify a second factor inside an existing session.

Account-changing endpoints depend on `require_recent_mfa`, which rejects a token
whose `mfa_time` is older than STEP_UP_MAX_AGE_SECONDS with 403 step_up_required.
The client then calls one of these endpoints; on success the cookie is re-issued
with a fresh `mfa_time` (and the ORIGINAL auth_time preserved, so the absolute
session ceiling and tokens_valid_after keep counting from the real login).
"""
import json
import logging
from datetime import datetime, timezone

import webauthn
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

from app.config import get_settings
from app.database import db
from app.dependencies import COOKIE_NAME, get_current_user
from app.limiter import _real_ip, limiter
from app.models.audit import AuditAction
from app.routers.auth import _set_auth_cookie
from app.routers.passkey import (
    _build_authentication_credential,
    _consume_challenge,
    _get_origin,
    _parse_transports,
    _store_challenge,
)
from app.services.auth_service import available_mfa_methods, record_auth_failure, verify_totp_for_user
from app.services.otp_service import send_email_otp, verify_email_otp
from app.services.token_service import create_access_token, decode_access_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth/step-up", tags=["step-up"])

STEP_UP_PURPOSE = "stepup"


async def _audit(user_id: int, action: AuditAction, request: Request, detail: dict | None = None) -> None:
    await db.execute(
        "INSERT INTO audit_log (user_id, action, detail, ip_address) VALUES (?, ?, ?, ?)",
        (user_id, action.value, json.dumps(detail) if detail else None, _real_ip(request)),
    )


@router.get("/methods")
@limiter.limit("30/minute")
async def step_up_methods(request: Request, current_user: dict = Depends(get_current_user)):
    """Which factors this session can use to step up."""
    return {"methods": await available_mfa_methods(current_user["id"])}


@router.post("/email/send")
@limiter.limit("3/minute")
async def step_up_send_email(request: Request, current_user: dict = Depends(get_current_user)):
    if "email_otp" not in await available_mfa_methods(current_user["id"]):
        raise HTTPException(status_code=400, detail="Email codes are not enabled for this account")
    try:
        await send_email_otp(current_user["id"], current_user["username"])
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"ok": True}


@router.post("/passkey/begin")
@limiter.limit("10/minute")
async def step_up_passkey_begin(request: Request, current_user: dict = Depends(get_current_user)):
    creds = await db.fetchall(
        "SELECT credential_id, transports FROM passkey_credentials WHERE user_id = ?",
        (current_user["id"],),
    )
    if not creds:
        raise HTTPException(status_code=400, detail="No passkeys registered for this account")
    s = get_settings()
    options = webauthn.generate_authentication_options(
        rp_id=s.rp_id,
        allow_credentials=[
            PublicKeyCredentialDescriptor(
                id=bytes(c["credential_id"]),
                transports=_parse_transports(json.loads(c["transports"] or "[]")) or None,
            )
            for c in creds
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    await _store_challenge(current_user["id"], options.challenge, STEP_UP_PURPOSE)
    return json.loads(webauthn.options_to_json(options))


class StepUpRequest(BaseModel):
    method: str
    code: str = ""
    credential: dict | None = None


@router.post("")
@limiter.limit("10/minute")
async def step_up(
    request: Request,
    response: Response,
    req: StepUpRequest,
    current_user: dict = Depends(get_current_user),
):
    uid = current_user["id"]
    methods = await available_mfa_methods(uid)
    if req.method not in methods:
        raise HTTPException(status_code=400, detail="That verification method is not enrolled")

    ok = False
    if req.method == "totp":
        ok = await verify_totp_for_user(uid, req.code.strip())
    elif req.method == "email_otp":
        ok = await verify_email_otp(uid, req.code.strip())
    elif req.method == "passkey":
        if not req.credential:
            raise HTTPException(status_code=400, detail="credential required")
        expected_challenge = await _consume_challenge(uid, STEP_UP_PURPOSE)
        s = get_settings()
        try:
            from webauthn.helpers import base64url_to_bytes
            cred_row = await db.fetchone(
                "SELECT id, public_key, sign_count FROM passkey_credentials WHERE user_id = ? AND credential_id = ?",
                (uid, base64url_to_bytes(req.credential["id"])),
            )
            if not cred_row:
                raise ValueError("unknown credential")
            verified = webauthn.verify_authentication_response(
                credential=_build_authentication_credential(req.credential),
                expected_challenge=expected_challenge,
                expected_rp_id=s.rp_id,
                expected_origin=_get_origin(request),
                credential_public_key=bytes(cred_row["public_key"]),
                credential_current_sign_count=cred_row["sign_count"],
                require_user_verification=True,
            )
            await db.execute(
                "UPDATE passkey_credentials SET sign_count = ?, last_used_at = ? WHERE id = ?",
                (verified.new_sign_count, datetime.now(timezone.utc).isoformat(), cred_row["id"]),
            )
            ok = True
        except Exception as exc:
            logger.warning("Step-up passkey verification failed for user %s: %s", uid, exc)
            ok = False

    if not ok:
        # Guessable factors count toward the same lockout as login failures.
        if req.method in ("totp", "email_otp"):
            await record_auth_failure(uid, _real_ip(request))
        await _audit(uid, AuditAction.STEP_UP_FAILURE, request, {"method": req.method})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Verification failed")

    # Re-issue the cookie: same original login (auth_time), fresh mfa_time.
    cookie = request.cookies.get(COOKIE_NAME)
    payload = decode_access_token(cookie) if cookie else None
    auth_time = payload.get("auth_time") if payload else None
    token = create_access_token(uid, auth_time=auth_time, mfa_time=datetime.now(timezone.utc).timestamp())
    _set_auth_cookie(response, token)
    await _audit(uid, AuditAction.STEP_UP_SUCCESS, request, {"method": req.method})
    return {"ok": True}
