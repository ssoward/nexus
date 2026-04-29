from enum import Enum
from dataclasses import dataclass
from typing import Optional


class AuditAction(str, Enum):
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    LOGIN_LOCKED = "LOGIN_LOCKED"
    LOGOUT = "LOGOUT"
    SESSION_CREATE = "SESSION_CREATE"
    SESSION_DELETE = "SESSION_DELETE"
    SESSION_START = "SESSION_START"
    SESSION_STOP = "SESSION_STOP"
    WS_CONNECT = "WS_CONNECT"
    WS_DISCONNECT = "WS_DISCONNECT"
    TOTP_SETUP = "TOTP_SETUP"
    PASSKEY_REGISTER = "PASSKEY_REGISTER"
    PASSKEY_AUTH_SUCCESS = "PASSKEY_AUTH_SUCCESS"
    PASSKEY_AUTH_FAILURE = "PASSKEY_AUTH_FAILURE"
    PASSKEY_DELETE = "PASSKEY_DELETE"


@dataclass
class AuditEntry:
    action: AuditAction
    user_id: Optional[int]
    detail: Optional[dict]
    ip_address: Optional[str]
