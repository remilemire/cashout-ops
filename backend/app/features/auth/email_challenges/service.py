# backend/app/features/auth/email_challenges/service.py

"""Email-challenge orchestration (passwordless sign-in).

Initiation stores a Redis challenge and emails a magic sign-in link;
visiting the link reveals a 6-digit code; entering the code in the
initiating tab consumes the challenge. Only SHA-256
hashes of the link token and the code reach the store — the plaintexts
exist solely in the email and on the link landing page.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import AppError
from app.features.users import service as users_service
from app.features.users.schemas import UserCreate
from app.infrastructure.outbox import service as outbox_service
from app.infrastructure.redis import Redis
from app.security.crypto import hash_secret_token

from . import store
from .model import StoredEmailChallenge
from .outbox import SEND_LOGIN_LINK_EMAIL_MAX_ATTEMPTS, send_login_link_email_message

if TYPE_CHECKING:
    from app.features.users.model import User

# Six numeric digits (leading zeros allowed).
CODE_DIGITS = 6
# Wrong-code guesses allowed before the challenge is destroyed.
MAX_CODE_ATTEMPTS = 5


def _generate_code() -> str:
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


async def initiate(db: AsyncSession, redis: Redis, *, email: str) -> str:
    """Start an email challenge for the address, returning the challenge id.

    Always succeeds: an unknown address gets a decoy id — neutral response,
    nothing stored, no email — indistinguishable from a real challenge, so
    the endpoint cannot be used for account enumeration. For a real user the
    challenge is stored in Redis and the link email is enqueued on the
    outbox, so it is sent only once the request commits.
    """
    user = await users_service.find_by_email(db, email=email)

    if user is None and email == settings.OWNER_EMAIL:
        # First sign-in bootstraps the owner account (there is no registration
        # step for it in the passwordless flow). Concurrent initiations can
        # race to a 409 on ix_users_email at commit; the loser simply retries
        # and finds the row, so it self-heals.
        user = await users_service.bootstrap_owner(
            db,
            payload=UserCreate(
                email=settings.OWNER_EMAIL, full_name=settings.OWNER_FULL_NAME
            ),
        )

    if user is None:
        return str(uuid4())  # decoy id

    challenge_id = str(uuid4())
    await store.save(
        redis,
        challenge_id=challenge_id,
        challenge=StoredEmailChallenge(user_id=user.id),
    )
    await outbox_service.enqueue(
        db,
        type=send_login_link_email_message.type,
        payload={"challenge_id": challenge_id, "user_id": str(user.id)},
        max_attempts=SEND_LOGIN_LINK_EMAIL_MAX_ATTEMPTS,
    )

    return challenge_id


async def verify_link(redis: Redis, *, challenge_id: str, token: str) -> str:
    """Confirm the emailed link and return a fresh one-time code.

    Repeatable and non-consuming: re-verifying supersedes the previous code
    (only the code's hash is stored), while `code_attempts` is preserved —
    the guess cap counts guesses from the initiating tab and must not reset
    on a re-click. Sign-in completes via `verify_code`.
    """
    challenge = await store.find(redis, challenge_id=challenge_id)

    if (
        challenge is None
        or challenge.token_hash is None
        or not secrets.compare_digest(challenge.token_hash, hash_secret_token(token))
    ):
        raise AppError("EMAIL_CHALLENGE_INVALID")

    code = _generate_code()
    challenge.code_hash = hash_secret_token(code)
    if not await store.update(redis, challenge_id=challenge_id, challenge=challenge):
        raise AppError("EMAIL_CHALLENGE_INVALID")

    return code


async def consume_code(
    db: AsyncSession, redis: Redis, *, challenge_id: str, code: str
) -> User:
    """Consume the challenge and return its user; the router completes
    sign-in via `access.grant`.

    Every failure mode raises the one unified error so the response shape
    cannot reveal whether a challenge, code, or account exists.
    """
    challenge = await store.find(redis, challenge_id=challenge_id)

    if challenge is None or challenge.code_hash is None:
        raise AppError("EMAIL_CHALLENGE_INVALID")

    if not secrets.compare_digest(challenge.code_hash, hash_secret_token(code)):
        challenge.code_attempts += 1
        if challenge.code_attempts >= MAX_CODE_ATTEMPTS:
            # Out of guesses: destroy the challenge outright.
            await store.delete(redis, challenge_id=challenge_id)
        else:
            await store.update(redis, challenge_id=challenge_id, challenge=challenge)
        raise AppError("EMAIL_CHALLENGE_INVALID")

    # The checked delete IS the consumption: losing the race means another
    # request already signed in with this challenge.
    if not await store.delete(redis, challenge_id=challenge_id):
        raise AppError("EMAIL_CHALLENGE_INVALID")

    user = await users_service.find_by_id(db, user_id=challenge.user_id)
    if user is None:
        # Deleted-user backstop: the account vanished after initiation.
        raise AppError("EMAIL_CHALLENGE_INVALID")

    return user


__all__ = ["initiate", "verify_link", "consume_code"]
