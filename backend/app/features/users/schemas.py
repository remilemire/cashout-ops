# backend/app/features/users/schemas.py

from __future__ import annotations

from pydantic import EmailStr, Field

from app.core.schemas import BaseIn, EntityOut, UtcDateTime


class UserOut(EntityOut):
    email: EmailStr
    full_name: str
    is_admin: bool
    is_active: bool
    email_verified_at: UtcDateTime | None = None


class UserCreate(BaseIn):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
