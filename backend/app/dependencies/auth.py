# backend/app/dependencies/auth.py

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.features.auth import service as auth_service
from app.features.sessions.cookies import get_session_cookie
from app.features.users.model import User
from app.features.users.types import UserRole

from .db import get_db


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    session_token = get_session_cookie(request)
    if session_token is None:
        raise AppError("UNAUTHENTICATED")

    context = await auth_service.authenticate(db, session_token=session_token)
    return context.user


def require_verified_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Guard for routes that require a confirmed email address.

    Not applied to any route yet; email verification currently only gates the
    UI (the frontend `EmailVerificationGate`).
    """
    if user.email_verified_at is None:
        raise AppError("EMAIL_NOT_VERIFIED")
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.ADMIN:
        raise AppError("FORBIDDEN", "Admin access required.")
    return user


__all__ = ["get_current_user", "require_admin", "require_verified_user"]
