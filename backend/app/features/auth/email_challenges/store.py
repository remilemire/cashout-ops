# backend/app/features/auth/email_challenges/store.py

"""Redis storage for email challenges.

- ``email_challenge:{challenge_id}`` holds a JSON-encoded
  :class:`StoredEmailChallenge` and expires after
  ``AUTH_CHALLENGE_TTL_MINUTES`` — Redis TTLs enforce expiry, so a missing
  key covers both "never issued" and "expired".
- ``email_challenge_email:{email_hash}`` points at the address's current
  challenge id, written alongside the challenge with the same TTL — it lets
  initiation find and destroy the address's previous challenge. Keyed by
  address rather than user id so it also covers the bootstrap owner address
  before its account exists, and by the address's digest to keep addresses
  out of key names (`service.email_key` owns that rule, and the per-email
  rate limiter keys on the same helper). That is not confidentiality — the
  challenge value under the adjacent key holds the plaintext address, which
  is what the code is emailed to.
- ``email_challenge_attempts:{challenge_id}`` is a server-atomic counter of
  code attempts with the same TTL; keeping it outside the challenge JSON is
  what makes the guess cap hold under concurrent requests.
- Updates use ``XX`` + ``KEEPTTL``, so a write can neither resurrect an
  expired challenge nor extend one beyond its initiation-time TTL.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import ValidationError

from app.core.config import settings
from app.infrastructure.redis import Redis

from .model import StoredEmailChallenge


def _challenge_key(challenge_id: str) -> str:
    return f"email_challenge:{challenge_id}"


def _email_pointer_key(email_hash: str) -> str:
    return f"email_challenge_email:{email_hash}"


def _attempts_key(challenge_id: str) -> str:
    return f"email_challenge_attempts:{challenge_id}"


async def save(
    redis: Redis, *, challenge_id: str, challenge: StoredEmailChallenge, email_hash: str
) -> None:
    """Store the challenge and point its address at it.

    `email_hash` is passed in rather than derived from `challenge.email`
    because `service.email_key` owns that rule; the address stays in the
    value, where it is needed to email the code and resolve the account.
    """
    ttl = timedelta(minutes=settings.auth.CHALLENGE_TTL_MINUTES)
    await redis.set(_challenge_key(challenge_id), challenge.model_dump_json(), ex=ttl)
    await redis.set(_email_pointer_key(email_hash), challenge_id, ex=ttl)


async def find(redis: Redis, *, challenge_id: str) -> StoredEmailChallenge | None:
    """The stored challenge, or None if absent/expired."""
    value = await redis.get(_challenge_key(challenge_id))

    if value is None:
        return None

    try:
        return StoredEmailChallenge.model_validate_json(str(value))
    except ValidationError:
        # A malformed stored value is treated as missing, mirroring expiry.
        return None


async def update(
    redis: Redis, *, challenge_id: str, challenge: StoredEmailChallenge
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


async def count_code_attempt(redis: Redis, *, challenge_id: str) -> int:
    """Atomically record a code attempt; returns this attempt's 1-based number.

    INCR is atomic on the server, so the guess cap holds under concurrency —
    a counter kept inside the challenge JSON was a GET/SET read-modify-write
    that racing requests could all read at 0. EXPIRE NX arms the TTL on the
    first attempt and heals an orphaned counter if a crash lands between the
    two commands. The counter can outlive a consumed or destroyed challenge
    by up to one TTL, which is harmless: challenge ids are never reused.
    """
    key = _attempts_key(challenge_id)
    count = await redis.incr(key)
    await redis.expire(  # pyright: ignore[reportUnknownMemberType]
        key, timedelta(minutes=settings.auth.CHALLENGE_TTL_MINUTES), nx=True
    )

    return int(count)


async def find_challenge_id_for_email(redis: Redis, *, email_hash: str) -> str | None:
    """The id of the address's current challenge, or None if absent/expired."""
    value = await redis.get(_email_pointer_key(email_hash))

    return None if value is None else str(value)


async def clear_email_pointer(
    redis: Redis, *, email_hash: str, challenge_id: str
) -> None:
    """Remove the address's pointer if it still points at ``challenge_id``.

    The GET+DEL pair can race a concurrent initiate (which rewrites the
    pointer between the two commands), but the race is benign: at worst a
    pointer or an orphaned challenge lingers until its ≤15-minute TTL.
    """
    value = await redis.get(_email_pointer_key(email_hash))

    if value is not None and str(value) == challenge_id:
        await redis.delete(_email_pointer_key(email_hash))


__all__ = [
    "save",
    "find",
    "update",
    "delete",
    "count_code_attempt",
    "find_challenge_id_for_email",
    "clear_email_pointer",
]
