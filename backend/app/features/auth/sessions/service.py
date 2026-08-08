# backend/app/features/auth/sessions/service.py

"""Session orchestration and token crypto.

The cookie carries the plaintext session token; this service mints tokens
and hashes them (SHA-256), so only token hashes ever reach the store.
"""

from __future__ import annotations

from uuid import UUID

from app.infrastructure.redis import Redis
from app.security.crypto import generate_secret_token, hash_secret_token

from . import store


async def create(redis: Redis, *, user_id: UUID) -> str:
    """Mint a session for the user and return the plaintext token."""
    session_token = generate_secret_token()

    await store.save(
        redis, token_hash=hash_secret_token(session_token), user_id=user_id
    )

    return session_token


async def find_user_id(redis: Redis, *, token: str) -> UUID | None:
    """The user id for a live session token, or None if absent/expired."""
    return await store.find_user_id(redis, token_hash=hash_secret_token(token))


async def delete_by_token(redis: Redis, *, token: str) -> None:
    await store.delete(redis, token_hash=hash_secret_token(token))


async def delete_all_for_user(redis: Redis, *, user_id: UUID) -> None:
    """Revoke every session belonging to the user."""
    await store.delete_all_for_user(redis, user_id=user_id)


__all__ = ["create", "find_user_id", "delete_by_token", "delete_all_for_user"]
