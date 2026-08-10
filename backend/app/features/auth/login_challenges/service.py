# backend/app/features/auth/login_challenges/service.py

"""Login-challenge orchestration (passwordless sign-in).

Initiation stores a Redis challenge and emails a magic sign-in link;
visiting the link reveals a 6-digit code; entering the code in the
initiating tab consumes the challenge and mints a session. Only SHA-256
hashes of the link token and the code reach the store — the plaintexts
exist solely in the email and on the link landing page.
"""

from __future__ import annotations

import logging
import secrets
from importlib.resources import files
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.errors import AppError
from app.features.auth.outbox import (
    SEND_LOGIN_LINK_EMAIL_MAX_ATTEMPTS,
    send_login_link_email_message,
)
from app.features.auth.sessions import service as sessions_service
from app.features.auth.types import UserWithSessionToken
from app.features.users import service as users_service
from app.features.users.schemas import UserCreate
from app.infrastructure.outbox import service as outbox_service
from app.infrastructure.redis import Redis
from app.integrations.email import EmailClient
from app.security.crypto import generate_secret_token, hash_secret_token

from . import store
from .store import StoredLoginChallenge

logger = logging.getLogger(__name__)

# Six numeric digits (leading zeros allowed).
CODE_DIGITS = 6
# Wrong-code guesses allowed before the challenge is destroyed.
MAX_CODE_ATTEMPTS = 5
_SUBJECT = "Your Whiskey District sign-in link"
# The email body template ships with this feature; render it with the link.
_TEMPLATE = (
    files("app.features.auth.login_challenges")
    .joinpath("templates", "login_link.html")
    .read_text(encoding="utf-8")
)


def _generate_code() -> str:
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


def _render_html(*, link: str, ttl_minutes: int) -> str:
    return _TEMPLATE.replace("{{link}}", link).replace(
        "{{ttl_minutes}}", str(ttl_minutes)
    )


async def initiate(db: AsyncSession, redis: Redis, *, email: str) -> str:
    """Start a login challenge for the email, returning the challenge id.

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
        return str(uuid4())

    challenge_id = str(uuid4())
    await store.save(
        redis,
        challenge_id=challenge_id,
        challenge=StoredLoginChallenge(user_id=user.id),
    )
    await outbox_service.enqueue(
        db,
        type=send_login_link_email_message.type,
        payload={"challenge_id": challenge_id, "user_id": str(user.id)},
        max_attempts=SEND_LOGIN_LINK_EMAIL_MAX_ATTEMPTS,
    )

    return challenge_id


async def send_login_link_email(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    *,
    email_client: EmailClient,
    challenge_id: str,
    user_id: UUID,
) -> None:
    """Outbox job: mint the link token and email the magic sign-in link.

    Runs from the outbox handler once the initiating request has committed,
    so it owns its session and transaction. The token hash is written to the
    challenge BEFORE the send: a retry regenerates and overwrites it, so the
    most recently emailed link is always the live one, and a crash between
    the write and the send never leaves an emailed-but-unstored token.
    """
    ttl_minutes = settings.LOGIN_CHALLENGE_TTL_MINUTES

    async with sessionmaker() as db:
        user = await users_service.find_by_id(db, user_id=user_id)
        if user is None:
            logger.info("Login link skipped: user %s no longer exists", user_id)
            return
        recipient = user.email

    challenge = await store.find(redis, challenge_id=challenge_id)
    if challenge is None:
        # Expired (or consumed) before delivery — stale work, not an error.
        logger.info("Login link skipped: challenge %s no longer exists", challenge_id)
        return

    token = generate_secret_token()
    challenge.token_hash = hash_secret_token(token)
    if not await store.update(redis, challenge_id=challenge_id, challenge=challenge):
        return  # expired mid-flight

    base_url = settings.APP_BASE_URL.rstrip("/")
    link = f"{base_url}/login/link?challenge={challenge_id}&token={token}"

    await email_client.send(
        to=recipient,
        subject=_SUBJECT,
        html=_render_html(link=link, ttl_minutes=ttl_minutes),
    )


async def verify_link(redis: Redis, *, challenge_id: str, token: str) -> str:
    """Confirm the emailed link and return a fresh one-time code.

    Repeatable and non-consuming: re-verifying supersedes the previous code
    (only the code's hash is stored), while `attempts` is preserved — the
    guess cap counts guesses from the initiating tab and must not reset on a
    re-click. Sign-in completes via `verify_code`.
    """
    challenge = await store.find(redis, challenge_id=challenge_id)

    if (
        challenge is None
        or challenge.token_hash is None
        or not secrets.compare_digest(challenge.token_hash, hash_secret_token(token))
    ):
        raise AppError("LOGIN_CHALLENGE_INVALID")

    code = _generate_code()
    challenge.code_hash = hash_secret_token(code)
    if not await store.update(redis, challenge_id=challenge_id, challenge=challenge):
        raise AppError("LOGIN_CHALLENGE_INVALID")

    return code


async def verify_code(
    db: AsyncSession, redis: Redis, *, challenge_id: str, code: str
) -> UserWithSessionToken:
    """Complete login: consume the challenge and mint a session.

    Every failure mode raises the one unified error so the response shape
    cannot reveal whether a challenge, code, or account exists.
    """
    challenge = await store.find(redis, challenge_id=challenge_id)

    if challenge is None or challenge.code_hash is None:
        raise AppError("LOGIN_CHALLENGE_INVALID")

    if not secrets.compare_digest(challenge.code_hash, hash_secret_token(code)):
        challenge.attempts += 1
        if challenge.attempts >= MAX_CODE_ATTEMPTS:
            # Out of guesses: destroy the challenge outright.
            await store.delete(redis, challenge_id=challenge_id)
        else:
            await store.update(redis, challenge_id=challenge_id, challenge=challenge)
        raise AppError("LOGIN_CHALLENGE_INVALID")

    # The checked delete IS the consumption: losing the race means another
    # request already signed in with this challenge.
    if not await store.delete(redis, challenge_id=challenge_id):
        raise AppError("LOGIN_CHALLENGE_INVALID")

    user = await users_service.find_by_id(db, user_id=challenge.user_id)
    if user is None:
        # Deleted-user backstop: the account vanished after initiation.
        raise AppError("LOGIN_CHALLENGE_INVALID")

    session_token = await sessions_service.create(redis, user_id=user.id)
    return UserWithSessionToken(user=user, session_token=session_token)


__all__ = ["initiate", "send_login_link_email", "verify_link", "verify_code"]
