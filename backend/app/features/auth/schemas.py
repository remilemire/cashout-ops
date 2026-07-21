# backend/app/features/auth/schemas.py

from __future__ import annotations

from pydantic import EmailStr, Field

from app.core.schemas import BaseIn


class AuthLogin(BaseIn):
    email: EmailStr
    password: str


class AuthRegister(BaseIn):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
