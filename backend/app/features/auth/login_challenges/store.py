# backend/app/features/auth/login_challenges/store.py

"""Redis storage for login challenges.

- ``login_challenge:{challenge_id}`` holds a JSON-encoded
  :class:`StoredLoginChallenge` and expires after
  ``LOGIN_CHALLENGE_TTL_MINUTES`` — Redis TTLs enforce expiry, so a missing
  key covers both "never issued" and "expired".
- Updates use ``XX`` + ``KEEPTTL``, so a write can neither resurrect an
  expired challenge nor extend one beyond its initiation-time TTL.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.infrastructure.redis import Redis


class StoredLoginChallenge(BaseModel):
    user_id: UUID
    token_hash: str | None = None
    code_hash: str | None = None
    attempts: int = 0


def _challenge_key(challenge_id: str) -> str:
    return f"login_challenge:{challenge_id}"


async def save(
    redis: Redis, *, challenge_id: str, challenge: StoredLoginChallenge
) -> None:
    await redis.set(
        _challenge_key(challenge_id),
        challenge.model_dump_json(),
        ex=timedelta(minutes=settings.LOGIN_CHALLENGE_TTL_MINUTES),
    )


async def find(redis: Redis, *, challenge_id: str) -> StoredLoginChallenge | None:
    """The stored challenge, or None if absent/expired."""
    value = await redis.get(_challenge_key(challenge_id))

    if value is None:
        return None

    try:
        return StoredLoginChallenge.model_validate_json(str(value))
    except ValidationError:
        # A malformed stored value is treated as missing, mirroring expiry.
        return None


async def update(
    redis: Redis, *, challenge_id: str, challenge: StoredLoginChallenge
) -> bool:
    """Overwrite an existing challenge; False if it no longer exists.

    XX refuses to resurrect an expired key; KEEPTTL anchors the challenge's
    lifetime to initiation rather than restarting it on every write.
    """
    reply = await redis.set(
        _challenge_key(challenge_id),
        challenge.model_dump_json(),
        xx=True,
        keepttl=True,
    )

    return bool(reply)


async def delete(redis: Redis, *, challenge_id: str) -> bool:
    """Delete the challenge; False if it was already gone.

    The checked delete is what makes consumption single-use under
    concurrency: of two racing consumers, only one observes the removal.
    """
    return await redis.delete(_challenge_key(challenge_id)) > 0


__all__ = ["StoredLoginChallenge", "save", "find", "update", "delete"]
