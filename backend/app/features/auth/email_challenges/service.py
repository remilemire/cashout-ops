# backend/app/features/auth/email_challenges/service.py

"""Email-challenge orchestration (passwordless sign-in).

Initiation stores a Redis challenge and emails a 6-digit sign-in code;
entering the code in the initiating tab consumes the challenge. Only the
SHA-256 hash of the code reaches the store — the plaintext exists solely
in the email.
"""

from __future__ import annotations

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
from app.security.crypto import hash_identifier, hash_secret_token

from . import store
from .model import StoredEmailChallenge
from .outbox import SEND_LOGIN_CODE_EMAIL_MAX_ATTEMPTS

if TYPE_CHECKING:
    from app.features.users.model import User

# Code submissions allowed per challenge, counted by an atomic Redis counter
# (`store.count_code_attempt`); a wrong guess at the cap destroys the challenge.
MAX_CODE_ATTEMPTS = 5


def email_key(email: str) -> str:
    """The address as it is keyed in Redis: normalized, then digested.

    Used by the challenge pointer here and by the per-email rate limiter in
    `dependencies.py`; both must agree, or casing variants of one address
    would split across two rate-limit buckets instead of sharing one.
    `normalize_email` is the same rule the users table is keyed on, so the
    Redis pointer and the account it stands for cannot disagree about which
    mailbox they mean. It is applied again here rather than assumed, since
    this helper also runs on an address read back out of Redis.

    Digesting is not a confidentiality measure — an address is low-entropy
    enough to recover from its digest, and the challenge value holds the
    plaintext anyway. It keeps addresses out of the surfaces that expose key
    names but not values (SCAN, MONITOR, the slowlog, per-key metrics).
    """
    return hash_identifier(normalize_email(email))


async def initiate(db: AsyncSession, redis: Redis, *, email: str) -> str:
    """Start an email challenge for the address, returning the challenge id.

    Always succeeds: an unknown address gets a decoy id — neutral response,
    nothing stored, no email — indistinguishable from a real challenge, so
    the endpoint cannot be used for account enumeration. For a real user the
    challenge is stored in Redis and the code email is enqueued on the
    outbox, so it is sent only once the request commits.

    Nothing is written to the users table here. BOOTSTRAP_OWNER_EMAIL is a
    valid recipient while it may still claim ownership, but the account is
    created only once the emailed code comes back (see `consume_code`) —
    creating it here would let any unauthenticated request mint the owner.
    The recipient test is the same one `consume_code` will apply, so an
    address that cannot sign in is never emailed a code that cannot work.
    """
    user = await users_service.find_by_email(db, email=email)

    if user is None and not await accounts.may_bootstrap_owner(db, email=email):
        return str(uuid4())  # decoy id

    # One active challenge per address: starting a new sign-in invalidates the
    # previous code. The Redis delete is not transactional with the
    # request, which is acceptable — worst case a rolled-back initiate
    # destroyed a previous challenge the user had already abandoned by
    # re-initiating.
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

    Accepting the code is this flow's mailbox proof — the code only exists
    in the email — so this is also where BOOTSTRAP_OWNER_EMAIL's account
    is created, rather than at initiation, where an unauthenticated request
    would have been enough to create it (see `accounts.resolve`).

    Every failure mode raises the one unified error so the response shape
    cannot reveal whether a challenge, code, or account exists.
    """
    challenge = await store.find(redis, challenge_id=challenge_id)

    # `code_hash is None` means the outbox handler has not minted and emailed
    # the code yet — nothing to compare, and no attempt is counted.
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
