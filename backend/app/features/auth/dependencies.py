# backend/app/features/auth/dependencies.py

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.features.users.model import User
from app.infrastructure.db.dependencies import get_db
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis
from app.security.cookies import get_session_cookie

from . import service as auth_service


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> User:
    session_token = get_session_cookie(request)
    if session_token is None:
        raise AppError("UNAUTHENTICATED")

    return await auth_service.authenticate(db, redis, session_token=session_token)


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise AppError("FORBIDDEN", "Admin access required.")
    return user


__all__ = ["get_current_user", "require_admin"]
