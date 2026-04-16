from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class User:
    id: int
    username: str
    hashed_password: str
    encrypted_totp_secret: bytes | None
    failed_login_count: int
    lockout_until: datetime | None
    created_at: datetime

    def __repr__(self) -> str:
        return f"User(id={self.id}, username={self.username!r})"


@dataclass
class UserPublic:
    id: int
    username: str
    created_at: str
