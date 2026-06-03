"""
auth/schemas.py — Pydantic request/response contracts for the auth API.

Email is validated with a small regex rather than pydantic's EmailStr so we
avoid pulling in the extra `email-validator` dependency.
"""

import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(v: str) -> str:
    v = (v or "").strip().lower()
    if not _EMAIL_RE.match(v):
        raise ValueError("Enter a valid email address")
    return v


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def _v_email(cls, v: str) -> str:
        return _normalize_email(v)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _v_email(cls, v: str) -> str:
        return _normalize_email(v)


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    watchlist: list[str] = []
    preferences: dict[str, Any] = {}
    portfolios: list[Any] = []
    created_at: Optional[str] = None
    last_login_at: Optional[str] = None


class AuthResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)


class UserDataUpdate(BaseModel):
    """Partial update for per-user personalization."""
    watchlist: Optional[list[str]] = None
    preferences: Optional[dict[str, Any]] = None
    portfolios: Optional[list[Any]] = None
