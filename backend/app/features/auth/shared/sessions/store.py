# backend/app/features/auth/shared/sessions/store.py

"""Redis storage for sessions.

Sessions live in Redis, not Postgres: ``session:{token_hash}`` holds a
JSON-encoded :class:`Session` and expires after ``SESSION_TTL`` — Redis
TTLs enforce expiry, so expired sessions vanish on their own.
"""

from __future__ import annotations

from pydantic import ValidationError

from app.infrastructure.redis import Redis

from .model import SESSION_TTL, Session


def _session_key(token_hash: str) -> str:
    return f"session:{token_hash}"


async def save(redis: Redis, *, token_hash: str, session: Session) -> None:
    await redis.set(_session_key(token_hash), session.model_dump_json(), ex=SESSION_TTL)


async def find(redis: Redis, *, token_hash: str) -> Session | None:
    """The session stored for the token hash, or None if absent/expired."""
    value = await redis.get(_session_key(token_hash))

    if value is None:
        return None

    try:
        return Session.model_validate_json(str(value))
    except ValidationError:
        # A malformed stored value is treated as missing, mirroring expiry.
        return None


async def delete(redis: Redis, *, token_hash: str) -> None:
    await redis.delete(_session_key(token_hash))


__all__ = ["save", "find", "delete"]
