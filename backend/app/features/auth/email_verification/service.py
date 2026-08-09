# backend/app/features/auth/email_verification/service.py

"""Email verification orchestration.

Issues 6-digit codes, emails them to the user, and confirms submitted
codes — marking the user verified and consuming the code on success. Only
the SHA-256 hash of a code reaches the store; the plaintext exists solely
in the email.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from importlib.resources import files
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.errors import AppError
from app.features.users import service as users_service
from app.features.users.model import User
from app.infrastructure.outbox import service as outbox_service
from app.infrastructure.redis import Redis
from app.integrations.email import EmailClient
from app.security.crypto import hash_secret_token

from ..outbox import (
    SEND_VERIFICATION_EMAIL_MAX_ATTEMPTS,
    send_verification_email_message,
)
from . import store

# Six numeric digits (leading zeros allowed).
_CODE_DIGITS = 6
_SUBJECT = "Your Whiskey District verification code"
# The email body template ships with this feature; render it with the code.
_TEMPLATE = (
    files("app.features.auth.email_verification")
    .joinpath("templates", "verify_email.html")
    .read_text(encoding="utf-8")
)


def _generate_code() -> str:
    return f"{secrets.randbelow(10**_CODE_DIGITS):0{_CODE_DIGITS}d}"


def _render_html(*, code: str, ttl_minutes: int) -> str:
    return _TEMPLATE.replace("{{code}}", code).replace(
        "{{ttl_minutes}}", str(ttl_minutes)
    )


async def send_new_code(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    *,
    email_client: EmailClient,
    user_id: UUID,
) -> None:
    """Outbox job: issue a fresh code and email it via the email client.

    Runs from the outbox handler once the triggering request (register/resend)
    has committed, so it owns its session and transaction. Supersedes any
    outstanding code. A send failure propagates so the outbox records it and
    retries; each attempt issues a fresh code whose hash overwrites the stored
    one, so the most recently emailed code is always the one that verifies.
    """
    ttl_minutes = settings.EMAIL_VERIFICATION_CODE_TTL_MINUTES

    async with sessionmaker() as db:
        user = await users_service.find_by_id(db, user_id=user_id)
        if user is None or user.email_verified_at is not None:
            return
        recipient = user.email

    code = _generate_code()
    await store.save_code_hash(
        redis, user_id=user_id, code_hash=hash_secret_token(code)
    )

    await email_client.send(
        to=recipient,
        subject=_SUBJECT,
        html=_render_html(code=code, ttl_minutes=ttl_minutes),
    )


async def resend(db: AsyncSession, *, user: User) -> None:
    """Queue a fresh verification code for the current user.

    Rejects an already-verified user. Otherwise enqueues the same outbox
    message `register` uses, in the caller's transaction, so the code is
    issued and the email sent only once the request commits.
    """
    if user.email_verified_at is not None:
        raise AppError("VERIFICATION_ALREADY_VERIFIED")

    await outbox_service.enqueue(
        db,
        type=send_verification_email_message.type,
        payload={"user_id": str(user.id)},
        max_attempts=SEND_VERIFICATION_EMAIL_MAX_ATTEMPTS,
    )


async def verify_email(
    db: AsyncSession, redis: Redis, *, user: User, code: str
) -> User:
    """Confirm a submitted code, marking the user verified on success."""
    if user.email_verified_at is not None:
        raise AppError("VERIFICATION_ALREADY_VERIFIED")

    stored_hash = await store.find_code_hash(redis, user_id=user.id)

    if stored_hash is None:
        # Redis TTL enforces expiry, so an expired code IS a missing key.
        raise AppError("VERIFICATION_CODE_EXPIRED")

    if not secrets.compare_digest(stored_hash, hash_secret_token(code)):
        raise AppError("VERIFICATION_CODE_INVALID")

    # Consume the code so it cannot be replayed.
    await store.delete(redis, user_id=user.id)
    user.email_verified_at = datetime.now(UTC)
    return user


async def delete_for_user(redis: Redis, *, user_id: UUID) -> None:
    """Drop any outstanding verification code for the user (e.g. on deletion)."""
    await store.delete(redis, user_id=user_id)


__all__ = ["resend", "send_new_code", "verify_email", "delete_for_user"]
