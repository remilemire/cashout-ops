# backend/app/features/auth/service.py

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.features.users import service as users_service
from app.infrastructure.redis import Redis

from .shared.sessions import service as sessions_service

if TYPE_CHECKING:
    from app.features.users.model import User


async def authenticate(db: AsyncSession, redis: Redis, *, session_token: str) -> User:
    session = await sessions_service.resolve_session(redis, token=session_token)

    if session is None:
        raise AppError("INVALID_SESSION")

    user = await users_service.find_by_id(db, user_id=session.user_id)

    if user is None:
        # The user row is gone (e.g. the account was deleted); the session is
        # dead even if its Redis key still lingers.
        raise AppError("INVALID_SESSION")

    return user


async def logout(redis: Redis, *, session_token: str) -> None:
    await sessions_service.delete_by_token(redis, token=session_token)
