"""Initiate email-code challenges and consume them to resolve a local account.

The challenge stores the code's hash. The outbox handler generates and
delivers the plaintext code after initiation commits.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas import normalize_email
from app.errors import AppError
from app.features.auth.shared import accounts
from app.features.users import service as users_service
from app.infrastructure.outbox import service as outbox_service
from app.infrastructure.redis import Redis
from app.security.crypto import hash_secret_token

from . import store
from .model import StoredEmailChallenge
from .outbox import SEND_LOGIN_CODE_EMAIL_MAX_ATTEMPTS

if TYPE_CHECKING:
    from app.features.users.model import User

# Code submissions allowed per challenge, counted by an atomic Redis counter
# (`store.count_code_attempt`); a wrong guess at the cap destroys the challenge.
MAX_CODE_ATTEMPTS = 5


def email_key(email: str) -> str:
    """Normalize and hash an address for its challenge pointer and rate-limit key.

    Both callers must use the same normalization to share one address bucket.
    Hashing keeps the address out of key names, but does not conceal it from
    readers of the stored challenge or from offline enumeration.
    """
    return hashlib.sha256(normalize_email(email).encode()).hexdigest()


async def initiate(db: AsyncSession, redis: Redis, *, email: str) -> str:
    """Return a challenge id without disclosing account existence in the result.

    Unknown addresses get a decoy id with no challenge or email enqueued.
    For eligible addresses, store a Redis challenge and enqueue code delivery
    in the database transaction. Infrastructure errors still propagate.

    The bootstrap address is eligible while it may claim ownership, but its
    account is created only after mailbox proof in `consume_code`. Eligibility
    is checked again at consumption because the account may change meanwhile.
    """
    user = await users_service.find_by_email(db, email=email)

    if user is None and not await accounts.may_bootstrap_owner(db, email=email):
        return str(uuid4())  # decoy id

    # Invalidate the challenge currently referenced by this address. Lookup,
    # deletion, and replacement are not atomic: concurrent initiations may
    # leave multiple live challenges. A later database rollback also does
    # not restore the previous Redis challenge.
    email_hash = email_key(email)
    previous_challenge_id = await store.find_challenge_id_for_email(
        redis, email_hash=email_hash
    )
    if previous_challenge_id is not None:
        await store.delete(redis, challenge_id=previous_challenge_id)

    challenge_id = str(uuid4())
    await store.save(
        redis,
        challenge_id=challenge_id,
        challenge=StoredEmailChallenge(email=email),
        email_hash=email_hash,
    )
    await outbox_service.enqueue(
        db,
        type="auth.send_login_code_email",
        payload={"challenge_id": challenge_id},
        max_attempts=SEND_LOGIN_CODE_EMAIL_MAX_ATTEMPTS,
    )

    return challenge_id


async def consume_code(
    db: AsyncSession, redis: Redis, *, challenge_id: str, code: str
) -> User:
    """Consume the challenge and return its user; the router completes
    sign-in via `access.grant`.

    A matching code is the mailbox proof required to create the bootstrap
    owner's account (see `accounts.resolve`). The caller presents a challenge
    id and code; this operation does not bind them to the initiating tab.

    Invalid, expired, exhausted, or consumed challenges and ineligible
    accounts share one error code. Infrastructure errors still propagate.
    """
    challenge = await store.find(redis, challenge_id=challenge_id)

    # No code has been stored yet, so there is nothing to compare and no
    # attempt is counted. A stored hash does not prove email delivery.
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
            await store.clear_email_pointer(
                redis,
                email_hash=email_key(challenge.email),
                challenge_id=challenge_id,
            )
        raise AppError("EMAIL_CHALLENGE_INVALID")

    # The checked delete IS the consumption: losing the race means another
    # request already signed in with this challenge.
    if not await store.delete(redis, challenge_id=challenge_id):
        raise AppError("EMAIL_CHALLENGE_INVALID")
    await store.clear_email_pointer(
        redis, email_hash=email_key(challenge.email), challenge_id=challenge_id
    )

    user = await accounts.resolve(db, email=challenge.email)
    if user is None:
        # The account vanished after initiation, the address may no longer
        # claim ownership, or the bootstrap lost a race to a concurrent
        # challenge for the same address. Rejecting the loser costs it one
        # fresh sign-in; all three surface as the one unified error.
        raise AppError("EMAIL_CHALLENGE_INVALID")

    return user


__all__ = ["email_key", "initiate", "consume_code"]
