# backend/app/features/sessions/service.py

# backend/app/services/sessions.py

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.lib.crypto import generate_secret_token, hash_secret_token

from .model import Session
from .types import SessionWithToken


async def find_valid_with_user(db: AsyncSession, *, token: str) -> Session | None:
    stmt = (
        select(Session)
        .options(joinedload(Session.user))
        .where(Session.token_hash == hash_secret_token(token))
    )

    session = (await db.execute(stmt)).scalar_one_or_none()

    if session is None:
        return None

    if session.expires_at < datetime.now(UTC).replace(tzinfo=None):
        return None

    return session


def create(db: AsyncSession, *, user_id: int) -> SessionWithToken:
    session_token = generate_secret_token()
    session_ttl = timedelta(days=settings.SESSION_TTL_DAYS)

    session = Session(
        token_hash=hash_secret_token(session_token),
        expires_at=datetime.now(UTC).replace(tzinfo=None) + session_ttl,
        user_id=user_id,
    )

    db.add(session)

    return SessionWithToken(session=session, session_token=session_token)


async def delete_by_token(db: AsyncSession, *, token: str) -> Session | None:
    stmt = select(Session).where(Session.token_hash == hash_secret_token(token))

    session = (await db.execute(stmt)).scalar_one_or_none()

    if session is None:
        return None

    await db.delete(session)

    return session


__all__ = ["find_valid_with_user", "create", "delete_by_token"]
