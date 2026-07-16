# backend/app/features/users/schemas.py

from __future__ import annotations

from pydantic import EmailStr, Field

from app.core.schemas import BaseIn, EntityOut

from .types import UserRole


class UserOut(EntityOut):
    email: EmailStr
    first_name: str
    last_name: str
    role: UserRole
    is_active: bool


class UserCreate(BaseIn):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
