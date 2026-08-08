# backend/app/features/auth/email_verification/store.py

"""Redis storage for email verification code hashes.

- ``email_verification:{user_id}`` holds the SHA-256 hash of the emailed
  6-digit code and expires after ``EMAIL_VERIFICATION_CODE_TTL_MINUTES`` —
  Redis TTLs enforce expiry, so a missing key covers both "never issued"
  and "expired".
- A plain SET overwrites any outstanding code, so each user has at most one
  active code and a resend invalidates the previous one.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from app.core.config import settings
from app.infrastructure.redis import Redis


def _verification_key(user_id: UUID | str) -> str:
    return f"email_verification:{user_id}"


async def save_code_hash(redis: Redis, *, user_id: UUID, code_hash: str) -> None:
    # SET overwrites: at most one active code per user, resend supersedes.
    await redis.set(
        _verification_key(user_id),
        code_hash,
        ex=timedelta(minutes=settings.EMAIL_VERIFICATION_CODE_TTL_MINUTES),
    )


async def find_code_hash(redis: Redis, *, user_id: UUID) -> str | None:
    """The stored code hash for the user, or None if absent/expired."""
    value = await redis.get(_verification_key(user_id))

    return None if value is None else str(value)


async def delete(redis: Redis, *, user_id: UUID) -> None:
    await redis.delete(_verification_key(user_id))


__all__ = ["save_code_hash", "find_code_hash", "delete"]
