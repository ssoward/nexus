import re
from pydantic import BaseModel, field_validator
from typing import Optional


class Workspace(BaseModel):
    id: int
    name: str
    color: str
    sort_order: int
    created_at: str


class WorkspaceCreate(BaseModel):
    name: str
    color: str = "#388bfd"

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 64:
            raise ValueError("Name must be 1-64 characters")
        return v

    @field_validator("color")
    @classmethod
    def color_valid(cls, v: str) -> str:
        if not re.match(r"^#[0-9a-fA-F]{6}$", v):
            raise ValueError("Color must be a hex color code (#rrggbb)")
        return v


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
