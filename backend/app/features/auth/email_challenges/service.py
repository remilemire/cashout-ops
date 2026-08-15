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


def _pointer_hash(email: str) -> str:
    """The address as it is keyed in Redis: hashed, so no PII lands in a key.

    Lowercased before hashing, matching the per-email rate limiter, so casing
    variants of one address share a pointer.
    """
    return hash_secret_token(email.lower())


async def _may_bootstrap_owner(db: AsyncSession, *, email: str) -> bool:
    """Whether this address may become the owner on a proven sign-in.

    Only the configured bootstrap address, and only while the deployment has
    no owner at all — the one state the single-owner invariant leaves open.
    A database that lost its owner therefore heals on the next sign-in
    there, while an address whose ownership has moved on is just another
    unknown one. Saying that outright beats attempting the insert and
    letting ix_users_single_owner reject it.

    It is a check, not a guarantee: two concurrent sign-ins can both pass
    here, so the index (and the SAVEPOINT in users' `add_if_unique`) stays
    the thing that actually holds the invariant.

    The address is compared first, so the ownership query runs only for it —
    never on an ordinary unknown-address probe.
    """
    if email != settings.bootstrap.OWNER_EMAIL:
        return False

    return not await users_service.owner_exists(db)


async def initiate(db: AsyncSession, redis: Redis, *, email: str) -> str:
    """Start an email challenge for the address, returning the challenge id.

    Always succeeds: an unknown address gets a decoy id — neutral response,
    nothing stored, no email — indistinguishable from a real challenge, so
    the endpoint cannot be used for account enumeration. For a real user the
    challenge is stored in Redis and the link email is enqueued on the
    outbox, so it is sent only once the request commits.

    Nothing is written to the users table here. BOOTSTRAP_OWNER_EMAIL is a
    valid recipient while it may still claim ownership, but the account is
    created only once the emailed link's code comes back (see
    `consume_code`) — creating it here would let any unauthenticated request
    mint the owner. The recipient test is the same one `consume_code` will
    apply, so an address that cannot sign in is never emailed a link that
    cannot work.
    """
    user = await users_service.find_by_email(db, email=email)

    if user is None and not await _may_bootstrap_owner(db, email=email):
        return str(uuid4())  # decoy id

    # One active challenge per address: starting a new sign-in invalidates the
    # previous link and code. The Redis delete is not transactional with the
    # request, which is acceptable — worst case a rolled-back initiate
    # destroyed a previous challenge the user had already abandoned by
    # re-initiating.
    email_hash = _pointer_hash(email)
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
        type="auth.send_login_link_email",
        payload={"challenge_id": challenge_id},
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
            await store.clear_email_pointer(
                redis,
                email_hash=_pointer_hash(challenge.email),
                challenge_id=challenge_id,
            )
        raise AppError("EMAIL_CHALLENGE_INVALID")

    # The checked delete IS the consumption: losing the race means another
    # request already signed in with this challenge.
    if not await store.delete(redis, challenge_id=challenge_id):
        raise AppError("EMAIL_CHALLENGE_INVALID")
    await store.clear_email_pointer(
        redis, email_hash=_pointer_hash(challenge.email), challenge_id=challenge_id
    )

    return await _resolve_user(db, email=challenge.email)


async def _resolve_user(db: AsyncSession, *, email: str) -> User:
    """The account behind a consumed challenge, bootstrapping the owner.

    This is the mailbox-proof point: the emailed link minted the code that
    was just accepted, so BOOTSTRAP_OWNER_EMAIL's account is created here
    rather than at initiation, where an unauthenticated request would have
    been enough to create it.

    Bootstrapping is gated on the deployment having no owner rather than on
    the deployment being new (`_may_bootstrap_owner`), so ownership is
    reclaimable after an out-of-band loss, and an address whose ownership
    has moved on is turned away here instead of at the unique index. It
    still cannot help once that address holds a non-owner row: the lookup
    below short-circuits, and no path promotes an existing account to OWNER
    (see users/types.py).
    """
    user = await users_service.find_by_email(db, email=email)

    if user is None and await _may_bootstrap_owner(db, email=email):
        # There is no registration step for the owner in the passwordless
        # flow, so its first proven sign-in creates the account.
        user = await users_service.bootstrap_owner(
            db,
            payload=UserCreate(
                email=settings.bootstrap.OWNER_EMAIL,
                full_name=settings.bootstrap.OWNER_FULL_NAME,
            ),
        )

    if user is None:
        # The account vanished after initiation, the address may no longer
        # claim ownership, or the bootstrap lost a race to a concurrent
        # challenge for the same address. Rejecting the loser costs it one
        # fresh sign-in; all three surface as the one unified error.
        raise AppError("EMAIL_CHALLENGE_INVALID")

    return user


__all__ = ["initiate", "consume_link", "consume_code"]
