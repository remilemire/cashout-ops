# backend/app/services/sessions.py

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import UnauthenticatedError
from app.models import Session
from app.utils.cookies import delete_cookie, set_cookie
from app.utils.csrf import clear_csrf_cookie, set_csrf_cookie

SESSION_COOKIE = "session_token"
LONG_SESSION_TTL = timedelta(days=7)
SHORT_SESSION_TTL = timedelta(hours=12)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(
    response: Response,
    db: AsyncSession,
    *,
    user_id: int,
    remember: bool = False,
) -> Session:
    token = secrets.token_urlsafe(32)
    ttl = LONG_SESSION_TTL if remember else SHORT_SESSION_TTL
    expires_at = datetime.now(UTC) + ttl

    session = Session(
        token_hash=_hash_token(token),
        user_id=user_id,
        expires_at=expires_at,
    )
    db.add(session)

    set_cookie(response, SESSION_COOKIE, token)
    set_csrf_cookie(response)
    return session


async def clear(
    request: Request,
    response: Response,
    db: AsyncSession,
) -> None:
    token = request.cookies.get(SESSION_COOKIE)

    if token is not None:
        stmt = select(Session).where(Session.token_hash == _hash_token(token))
        session = (await db.execute(stmt)).scalar_one_or_none()

        if session is not None:
            await db.delete(session)

    delete_cookie(response, SESSION_COOKIE)
    clear_csrf_cookie(response)


async def get_user_id(request: Request, db: AsyncSession) -> int:
    token = request.cookies.get(SESSION_COOKIE)

    if token is None:
        raise UnauthenticatedError()

    stmt = select(Session).where(Session.token_hash == _hash_token(token))
    session = (await db.execute(stmt)).scalar_one_or_none()

    if session is None:
        raise UnauthenticatedError()

    if session.expires_at <= datetime.now(UTC).replace(tzinfo=None):
        raise UnauthenticatedError("session expired")

    return session.user_id
