# backend/app/schemas/auth.py

from __future__ import annotations

from pydantic import EmailStr, Field

from .base import BaseIn


class AuthLogin(BaseIn):
    email: EmailStr
    password: str


class AuthRegister(BaseIn):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)
