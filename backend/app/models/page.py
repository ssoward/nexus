from pydantic import BaseModel, field_validator
from typing import Optional


class Page(BaseModel):
    id: int
    name: str
    url: str
    position: int
    created_at: str


class PageCreate(BaseModel):
    name: str
    url: str

    @field_validator("url")
    @classmethod
    def url_https_only(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("https://"):
            raise ValueError("Only HTTPS URLs are allowed")
        if len(v) > 2048:
            raise ValueError("URL must be 2048 characters or fewer")
        return v

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 64:
            raise ValueError("Name must be 1-64 characters")
        return v


class PageUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    position: Optional[int] = None

    @field_validator("url")
    @classmethod
    def url_https_only(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("https://"):
            raise ValueError("Only HTTPS URLs are allowed")
        if len(v) > 2048:
            raise ValueError("URL must be 2048 characters or fewer")
        return v

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 64:
            raise ValueError("Name must be 1-64 characters")
        return v
