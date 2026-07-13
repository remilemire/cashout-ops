# backend/app/features/users/schemas.py

from __future__ import annotations

from pydantic import EmailStr, Field

from app.core.schemas import BaseIn, EntityOut


class UserOut(EntityOut):
    # TODO
    pass


class UserCreate(BaseIn):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
