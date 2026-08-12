# backend/app/features/auth/shared/sessions/service.py

"""Session orchestration and token crypto.

The cookie carries the plaintext session token; this service mints tokens
and hashes them (SHA-256), so only token hashes ever reach the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.config import settings
from app.infrastructure.redis import Redis
from app.security.crypto import generate_secret_token, hash_secret_token

from . import store
from .model import Session


@dataclass(frozen=True)
class IssuedSession:
    """A freshly minted session plus its plaintext token (never stored)."""

    session: Session
    token: str


async def create(redis: Redis, *, user_id: UUID) -> IssuedSession:
    """Mint a session for the user and return it with the plaintext token."""
    token = generate_secret_token()
    issued_at = datetime.now(UTC)
    session = Session(
        user_id=user_id,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(days=settings.auth.SESSION_TTL_DAYS),
    )

    await store.save(redis, token_hash=hash_secret_token(token), session=session)

    return IssuedSession(session=session, token=token)


async def resolve_session(redis: Redis, *, token: str) -> Session | None:
    """The live session for the token, or None if absent/expired."""
    return await store.find(redis, token_hash=hash_secret_token(token))


async def delete_by_token(redis: Redis, *, token: str) -> None:
    await store.delete(redis, token_hash=hash_secret_token(token))


__all__ = ["IssuedSession", "create", "resolve_session", "delete_by_token"]
