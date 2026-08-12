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
from .outbox import SEND_LOGIN_LINK_EMAIL_MAX_ATTEMPTS

if TYPE_CHECKING:
    from app.features.users.model import User

# Six numeric digits (leading zeros allowed).
CODE_DIGITS = 6
# Code submissions allowed per challenge, counted by an atomic Redis counter
# (`store.count_code_attempt`); a wrong guess at the cap destroys the challenge.
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

    # One active challenge per user: starting a new sign-in invalidates the
    # previous link and code. The Redis delete is not transactional with the
    # request, which is acceptable — worst case a rolled-back initiate
    # destroyed a previous challenge the user had already abandoned by
    # re-initiating.
    previous_challenge_id = await store.find_challenge_id_for_user(
        redis, user_id=user.id
    )
    if previous_challenge_id is not None:
        await store.delete(redis, challenge_id=previous_challenge_id)

    challenge_id = str(uuid4())
    await store.save(
        redis,
        challenge_id=challenge_id,
        challenge=StoredEmailChallenge(user_id=user.id),
    )
    await outbox_service.enqueue(
        db,
        type="auth.send_login_link_email",
        payload={"challenge_id": challenge_id, "user_id": str(user.id)},
        max_attempts=SEND_LOGIN_LINK_EMAIL_MAX_ATTEMPTS,
    )

    return challenge_id


async def consume_link(redis: Redis, *, challenge_id: str, token: str) -> str:
    """Confirm the emailed link and return a fresh one-time code.

    The link is single-use: verifying clears `token_hash` in the same write
    that stores the code's hash, so a second verify with the same token is
    rejected. The challenge itself survives — `consume_code` still needs it —
    and the atomic attempt counter keyed by the challenge id keeps counting
    guesses from the initiating tab. Sign-in completes via `verify_code`.
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
    # Verifying consumes the link: with the hash cleared, a replayed link
    # hits the `token_hash is None` branch above.
    challenge.token_hash = None
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

    attempt = await store.count_code_attempt(redis, challenge_id=challenge_id)
    if attempt > MAX_CODE_ATTEMPTS:
        # Budget checked before the compare: at most MAX_CODE_ATTEMPTS requests
        # ever reach compare_digest, even when guesses race concurrently.
        raise AppError("EMAIL_CHALLENGE_INVALID")

    if not secrets.compare_digest(challenge.code_hash, hash_secret_token(code)):
        if attempt >= MAX_CODE_ATTEMPTS:
            # Out of guesses: destroy the challenge outright.
            await store.delete(redis, challenge_id=challenge_id)
            await store.clear_user_pointer(
                redis, user_id=challenge.user_id, challenge_id=challenge_id
            )
        raise AppError("EMAIL_CHALLENGE_INVALID")

    # The checked delete IS the consumption: losing the race means another
    # request already signed in with this challenge.
    if not await store.delete(redis, challenge_id=challenge_id):
        raise AppError("EMAIL_CHALLENGE_INVALID")
    await store.clear_user_pointer(
        redis, user_id=challenge.user_id, challenge_id=challenge_id
    )

    user = await users_service.find_by_id(db, user_id=challenge.user_id)
    if user is None:
        # Deleted-user backstop: the account vanished after initiation.
        raise AppError("EMAIL_CHALLENGE_INVALID")

    return user


__all__ = ["initiate", "consume_link", "consume_code"]
