# backend/app/features/auth/shared/sessions/store.py

"""Redis storage for sessions.

Sessions live in Redis, not Postgres, under two key shapes:

- ``session:{token_hash}`` holds the user id and expires after
  ``SESSION_TTL_DAYS`` — Redis TTLs enforce expiry, so expired sessions
  vanish on their own (the old ``sessions`` table never deleted its
  expired rows).
- ``user_sessions:{user_id}`` is a set of the user's token hashes so all of
  a user's sessions can be revoked without scanning the keyspace. Stale
  members are harmless: deleting an already-expired session key is a no-op.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from app.core.config import settings
from app.infrastructure.redis import Redis


def _session_key(token_hash: str) -> str:
    return f"session:{token_hash}"


def _user_sessions_key(user_id: UUID | str) -> str:
    return f"user_sessions:{user_id}"


async def save(redis: Redis, *, token_hash: str, user_id: UUID) -> None:
    """Store the session and index it in the user's session set."""
    session_ttl = timedelta(days=settings.SESSION_TTL_DAYS)

    await redis.set(_session_key(token_hash), str(user_id), ex=session_ttl)

    # Refresh the index set's TTL on every add so it outlives its newest
    # member; members whose session keys have expired are ignored on revoke.
    index_key = _user_sessions_key(user_id)
    await redis.sadd(index_key, token_hash)
    await redis.expire(index_key, session_ttl)


async def find_user_id(redis: Redis, *, token_hash: str) -> UUID | None:
    """The user id stored for the token hash, or None if absent/expired."""
    value = await redis.get(_session_key(token_hash))

    if value is None:
        return None

    try:
        return UUID(str(value))
    except ValueError:  # malformed stored value: treat as no session
        return None


async def delete(redis: Redis, *, token_hash: str) -> None:
    session_key = _session_key(token_hash)

    # Read the user id first so the index set can be pruned too.
    user_id = await redis.get(session_key)

    await redis.delete(session_key)

    if user_id is not None:
        await redis.srem(_user_sessions_key(str(user_id)), token_hash)


async def delete_all_for_user(redis: Redis, *, user_id: UUID) -> None:
    """Delete every session key belonging to the user, plus the index."""
    index_key = _user_sessions_key(user_id)

    token_hashes = await redis.smembers(index_key)

    if token_hashes:
        await redis.delete(*(_session_key(str(h)) for h in token_hashes))

    await redis.delete(index_key)


__all__ = ["save", "find_user_id", "delete", "delete_all_for_user"]
