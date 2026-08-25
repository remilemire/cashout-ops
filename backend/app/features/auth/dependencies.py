# backend/app/features/auth/dependencies.py

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.features.auth.sessions.dependencies import get_current_session
from app.features.auth.sessions.model import Session
from app.features.users import service as users_service
from app.features.users.model import User
from app.features.users.types import UserRole
from app.infrastructure.db.dependencies import get_db


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    session: Annotated[Session, Depends(get_current_session)],
) -> User:
    user = await users_service.find_by_id(db, user_id=session.user_id)

    if user is None:
        # The user row is gone (e.g. the account was deleted); the session is
        # dead even if its Redis key still lingers.
        raise AppError("INVALID_SESSION")

    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Admins and the owner both pass."""
    if user.role not in (UserRole.ADMIN, UserRole.OWNER):
        raise AppError("FORBIDDEN", "Admin access required.")
    return user


def require_owner(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role is not UserRole.OWNER:
        raise AppError("FORBIDDEN", "Owner access required.")
    return user


__all__ = ["get_current_user", "require_admin", "require_owner"]
