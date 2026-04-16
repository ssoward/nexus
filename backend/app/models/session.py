import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, field_validator
from typing import Optional


class SessionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    RECOVERY_PENDING = "recovery_pending"


@dataclass
class Session:
    id: str
    user_id: int
    name: str
    image: str
    container_id: Optional[str]
    container_name: str
    status: SessionStatus
    cols: int
    rows: int
    created_at: str
    last_active_at: str


class SessionCreate(BaseModel):
    name: str
    image: str
    cols: int = 80
    rows: int = 24

    @field_validator("image")
    @classmethod
    def image_valid(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 64:
            raise ValueError("Preset name must be 1–64 characters")
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("Preset name may only contain letters, digits, _, -")
        return v

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Session name cannot be empty")
        if len(v) > 64:
            raise ValueError("Session name must be 64 characters or fewer")
        return v

    @field_validator("cols")
    @classmethod
    def cols_range(cls, v: int) -> int:
        if not (20 <= v <= 500):
            raise ValueError("cols must be between 20 and 500")
        return v

    @field_validator("rows")
    @classmethod
    def rows_range(cls, v: int) -> int:
        if not (5 <= v <= 200):
            raise ValueError("rows must be between 5 and 200")
        return v


class SessionPublic(BaseModel):
    id: str
    name: str
    image: str
    status: SessionStatus
    cols: int
    rows: int
    created_at: str
    last_active_at: str


class SessionResizeRequest(BaseModel):
    cols: int
    rows: int

    @field_validator("cols")
    @classmethod
    def cols_range(cls, v: int) -> int:
        if not (20 <= v <= 500):
            raise ValueError("cols must be between 20 and 500")
        return v

    @field_validator("rows")
    @classmethod
    def rows_range(cls, v: int) -> int:
        if not (5 <= v <= 200):
            raise ValueError("rows must be between 5 and 200")
        return v
