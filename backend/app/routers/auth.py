import io
import json
import base64
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import pyotp
import qrcode
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from pydantic import BaseModel, field_validator

from app.config import get_settings
from app.crypto import encrypt_totp_secret, hash_password
from app.database import db
from app.dependencies import get_current_user
from app.limiter import limiter
from app.services.auth_service import authenticate_user, NEEDS_TOTP, NEEDS_MFA_SETUP, NEEDS_EMAIL_OTP
from app.services.token_service import create_access_token, create_ws_token, decode_access_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

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


@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    totp_code: str = Form(default=""),
):
    ip = request.client.host if request.client else None
    user = await authenticate_user(username, password, totp_code, ip)

    if user == NEEDS_MFA_SETUP:
        return {"ok": False, "needs_mfa_setup": True}

    if user == NEEDS_TOTP:
        return {"ok": False, "needs_totp": True}

    if user == NEEDS_EMAIL_OTP:
        return {"ok": False, "needs_email_otp": True}

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or account locked",
        )

    token = create_access_token(user["id"])
    _set_auth_cookie(response, token)
    return {"ok": True, "username": user["username"]}


MAX_SESSION_SECONDS = 24 * 60 * 60  # Absolute session lifetime: 24 hours


@router.post("/refresh")
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    """
    Re-issue the access-token cookie while the user is still active.
    The frontend calls this every 30 minutes so a session never expires
    mid-use. Enforces a 24-hour absolute session lifetime — after that
    the user must re-authenticate.
    """
    # Propagate auth_time from the current token to enforce absolute lifetime
    cookie = request.cookies.get(COOKIE_NAME)
    auth_time = None
    if cookie:
        payload = decode_access_token(cookie)
        if payload:
            auth_time = payload.get("auth_time")
    if auth_time and (datetime.now(timezone.utc).timestamp() - auth_time > MAX_SESSION_SECONDS):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired — please sign in again",
        )
    token = create_access_token(current_user["id"], auth_time=auth_time)
    _set_auth_cookie(response, token)
    return {"ok": True}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    # Revoke the JWT so it can't be reused even before expiry (HIGH-3)
    token = request.cookies.get(COOKIE_NAME)
    if token:
        payload = decode_access_token(token)
        if payload:
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
                await db.execute(
                    "INSERT OR IGNORE INTO revoked_tokens (jti, user_id, expires_at) VALUES (?, ?, ?)",
                    (jti, current_user["id"], expires_at),
                )

    await db.execute(
        "INSERT INTO audit_log (user_id, action, ip_address) VALUES (?, ?, ?)",
        (current_user["id"], "LOGOUT", request.client.host if request.client else None),
    )
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}


class WsTokenResponse(BaseModel):
    ws_token: str


@router.post("/ws-token", response_model=WsTokenResponse)
@limiter.limit("60/minute")
async def get_ws_token(
    request: Request,
    session_id: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    # Verify session belongs to this user
    row = await db.fetchone(
        "SELECT id FROM sessions WHERE id = ? AND user_id = ?",
        (session_id, current_user["id"]),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    token, jti, expires_at = create_ws_token(current_user["id"], session_id)
    await db.execute(
        "INSERT INTO ws_tokens (jti, user_id, session_id, expires_at) VALUES (?, ?, ?, ?)",
        (jti, current_user["id"], session_id, expires_at.isoformat()),
    )
    return WsTokenResponse(ws_token=token)


class TotpSetupResponse(BaseModel):
    provisioning_uri: str
    qr_code_base64: str


@router.post("/setup-totp", response_model=TotpSetupResponse)
async def setup_totp(
    request: Request,
    current_user: dict = Depends(get_current_user),
    totp_code: str = Form(default=""),
):
    """
    Set up TOTP for the authenticated user.
    Only callable by the user for their own account (auth cookie required).
    If TOTP is already configured, the current code must be provided to authorize
    the replacement — prevents an attacker with a hijacked session from locking
    out the real user.
    """
    s = get_settings()

    # If TOTP is already set up, require re-authentication with the current code
    row = await db.fetchone(
        "SELECT encrypted_totp_secret FROM users WHERE id = ?",
        (current_user["id"],),
    )
    if row and row["encrypted_totp_secret"] is not None:
        if not totp_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Current TOTP code required to replace existing authenticator",
            )
        from app.crypto import decrypt_totp_secret
        try:
            existing_secret = decrypt_totp_secret(bytes(row["encrypted_totp_secret"]), current_user["id"])
        except Exception:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="TOTP decryption error")
        if not pyotp.TOTP(existing_secret).verify(totp_code, valid_window=1):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid TOTP code",
            )

    secret = pyotp.random_base32()
    encrypted = encrypt_totp_secret(secret, current_user["id"])
    await db.execute(
        "UPDATE users SET encrypted_totp_secret = ? WHERE id = ?",
        (encrypted, current_user["id"]),
    )
    await db.execute(
        "INSERT INTO audit_log (user_id, action, ip_address) VALUES (?, ?, ?)",
        (current_user["id"], "TOTP_SETUP", request.client.host if request.client else None),
    )

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user["username"], issuer_name=s.totp_issuer)

    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return TotpSetupResponse(provisioning_uri=uri, qr_code_base64=qr_b64)


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {"id": current_user["id"], "username": current_user["username"]}


class CreateUserRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) < 5 or len(v) > 254:
            raise ValueError("Email must be 5-254 characters")
        if not re.match(r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$", v):
            raise ValueError("Must be a valid email address")
        return v

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if len(v) < 16:
            raise ValueError("Password must be at least 16 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Password must contain at least one special character")
        return v


@router.post("/bootstrap-totp", response_model=TotpSetupResponse)
@limiter.limit("5/minute")
async def bootstrap_totp(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """
    Bootstrap endpoint: set up TOTP for a user that has no TOTP secret yet.
    Only works if the user has no encrypted_totp_secret (one-time setup).
    Requires correct username + password to authorize.
    """
    s = get_settings()
    row = await db.fetchone(
        "SELECT id, hashed_password, encrypted_totp_secret FROM users WHERE username = ?",
        (username,),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    from app.crypto import verify_password as vp
    if not vp(password, row["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if row["encrypted_totp_secret"] is not None:
        # Return 401 (same as bad credentials) to prevent user enumeration
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    secret = pyotp.random_base32()
    encrypted = encrypt_totp_secret(secret, row["id"])
    await db.execute(
        "UPDATE users SET encrypted_totp_secret = ? WHERE id = ?",
        (encrypted, row["id"]),
    )
    await db.execute(
        "INSERT INTO audit_log (user_id, action, ip_address) VALUES (?, ?, ?)",
        (row["id"], "TOTP_SETUP", request.client.host if request.client else None),
    )

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=username, issuer_name=s.totp_issuer)

    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return TotpSetupResponse(provisioning_uri=uri, qr_code_base64=qr_b64)


@router.post("/create-user")
@limiter.limit("5/minute")
async def create_user(request: Request, req: CreateUserRequest):
    """Register a new account. After creation, the user must set up MFA."""
    user_count = await db.fetchone("SELECT COUNT(*) AS n FROM users")
    if user_count and user_count["n"] > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is closed — this instance already has an owner",
        )
    existing = await db.fetchone(
        "SELECT id FROM users WHERE username = ?", (req.username,)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    hashed = hash_password(req.password)
    await db.execute(
        "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
        (req.username, hashed),
    )
    await db.execute(
        "INSERT INTO audit_log (user_id, action, ip_address) "
        "SELECT id, 'USER_CREATE', ? FROM users WHERE username = ?",
        (request.client.host if request.client else None, req.username),
    )
    return {"ok": True, "message": "Account created. Set up MFA to continue."}


@router.post("/setup-mfa")
@limiter.limit("5/minute")
async def setup_mfa(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    method: str = Form(...),
):
    """Choose and configure MFA method (totp or email_otp). Requires valid credentials."""
    if method not in ("totp", "email_otp"):
        raise HTTPException(status_code=400, detail="method must be 'totp' or 'email_otp'")

    row = await db.fetchone(
        "SELECT id, hashed_password, mfa_method FROM users WHERE username = ?",
        (username,),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    from app.crypto import verify_password as vp
    if not vp(password, row["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if row["mfa_method"] is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA already configured")

    s = get_settings()
    ip = request.client.host if request.client else None

    if method == "totp":
        secret = pyotp.random_base32()
        encrypted = encrypt_totp_secret(secret, row["id"])
        await db.execute(
            "UPDATE users SET encrypted_totp_secret = ?, mfa_method = 'totp' WHERE id = ?",
            (encrypted, row["id"]),
        )
        await db.execute(
            "INSERT INTO audit_log (user_id, action, ip_address) VALUES (?, ?, ?)",
            (row["id"], "MFA_SETUP_TOTP", ip),
        )
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=username, issuer_name=s.totp_issuer)
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
        return {"method": "totp", "provisioning_uri": uri, "qr_code_base64": qr_b64}

    else:  # email_otp
        await db.execute(
            "UPDATE users SET mfa_method = 'email_otp' WHERE id = ?",
            (row["id"],),
        )
        await db.execute(
            "INSERT INTO audit_log (user_id, action, ip_address) VALUES (?, ?, ?)",
            (row["id"], "MFA_SETUP_EMAIL_OTP", ip),
        )
        from app.services.otp_service import send_email_otp
        await send_email_otp(row["id"], username)
        return {"method": "email_otp", "message": "Verification code sent to your email"}


@router.post("/resend-otp")
@limiter.limit("3/minute")
async def resend_otp(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Resend email OTP code. Requires valid credentials."""
    row = await db.fetchone(
        "SELECT id, hashed_password, mfa_method FROM users WHERE username = ?",
        (username,),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    from app.crypto import verify_password as vp
    if not vp(password, row["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if row["mfa_method"] != "email_otp":
        raise HTTPException(status_code=400, detail="Email OTP not configured for this account")

    from app.services.otp_service import send_email_otp
    await send_email_otp(row["id"], username)
    return {"ok": True, "message": "Code resent"}


@router.post("/switch-mfa")
@limiter.limit("5/minute")
async def switch_mfa(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    method: str = Form(...),
):
    """Switch MFA method. Requires valid credentials. Used from the login page
    when a user wants to verify with a different method than their default."""
    if method not in ("totp", "email_otp"):
        raise HTTPException(status_code=400, detail="method must be 'totp' or 'email_otp'")

    row = await db.fetchone(
        "SELECT id, hashed_password, mfa_method, encrypted_totp_secret FROM users WHERE username = ?",
        (username,),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    from app.crypto import verify_password as vp
    if not vp(password, row["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    s = get_settings()

    if method == "totp":
        if not row["encrypted_totp_secret"]:
            # Need to set up TOTP from scratch
            secret = pyotp.random_base32()
            encrypted = encrypt_totp_secret(secret, row["id"])
            await db.execute(
                "UPDATE users SET encrypted_totp_secret = ?, mfa_method = 'totp' WHERE id = ?",
                (encrypted, row["id"]),
            )
            totp = pyotp.TOTP(secret)
            uri = totp.provisioning_uri(name=username, issuer_name=s.totp_issuer)
            img = qrcode.make(uri)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            qr_b64 = base64.b64encode(buf.getvalue()).decode()
            return {"method": "totp", "needs_setup": True, "provisioning_uri": uri, "qr_code_base64": qr_b64}
        else:
            await db.execute("UPDATE users SET mfa_method = 'totp' WHERE id = ?", (row["id"],))
            return {"method": "totp", "needs_setup": False}

    else:  # email_otp
        await db.execute("UPDATE users SET mfa_method = 'email_otp' WHERE id = ?", (row["id"],))
        from app.services.otp_service import send_email_otp
        await send_email_otp(row["id"], username)
        return {"method": "email_otp", "needs_setup": False}
