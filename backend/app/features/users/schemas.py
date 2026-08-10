# backend/app/features/users/schemas.py

from __future__ import annotations

import uuid

from pydantic import EmailStr, Field

from app.core.schemas import BaseIn, BaseOut, UtcDateTime

from .types import UserRole


class UserOut(BaseOut):
    id: uuid.UUID
    created_at: UtcDateTime
    email: EmailStr
    full_name: str
    role: UserRole


class UserCreate(BaseIn):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)


class UserUpdate(BaseIn):
    full_name: str = Field(min_length=1, max_length=200)
