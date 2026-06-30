# backend/app/api/dependencies.py

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cookies import get_csrf_cookie, get_csrf_header, get_session_cookie
from app.errors import ForbiddenError, UnauthorizedError
from app.models import User
from app.models.enums import UserRole
from app.services import auth

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


# ================================
# ----------- Database -----------
# ================================


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db_sessionmaker() as db:
        try:
            yield db
            await db.commit()
        except BaseException:
            await db.rollback()
            raise


# ================================
# ------------- Auth -------------
# ================================


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    session_token = get_session_cookie(request)
    if session_token is None:
        raise UnauthorizedError("Authentication required.")

    context = await auth.authenticate(db, session_token=session_token)
    return context.user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.ADMIN:
        raise ForbiddenError("Admin access required.")
    return user


# ================================
# ------------- CSRF -------------
# ================================


def require_csrf(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return

    cookie_token = get_csrf_cookie(request)
    header_token = get_csrf_header(request)
    if cookie_token is None or header_token is None or cookie_token != header_token:
        raise ForbiddenError("Invalid CSRF token.")
