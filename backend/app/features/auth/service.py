# backend/app/features/auth/service.py

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import AppError
from app.features.invitations import service as invitations_service
from app.features.users import service as users_service
from app.features.users.schemas import UserCreate
from app.infrastructure.outbox import service as outbox_service
from app.infrastructure.redis import Redis
from app.security.passwords import hash_password, verify_password

from .outbox import (
    SEND_VERIFICATION_EMAIL_MAX_ATTEMPTS,
    send_verification_email_message,
)
from .schemas import AuthLogin, AuthRegister
from .sessions import service as sessions_service
from .types import UserWithSessionToken

if TYPE_CHECKING:
    from app.features.users.model import User


async def login(
    db: AsyncSession, redis: Redis, *, payload: AuthLogin
) -> UserWithSessionToken:
    user = await users_service.find_by_email(db, email=payload.email)

    if user is None:
        raise AppError("INVALID_CREDENTIALS")

    if not verify_password(payload.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS")

    session_token = await sessions_service.create(redis, user_id=user.id)
    return UserWithSessionToken(user=user, session_token=session_token)


async def register(
    db: AsyncSession,
    redis: Redis,
    *,
    payload: AuthRegister,
) -> UserWithSessionToken:
    """Create an account, start a session, and queue a verification email.

    Registration requires a pending invitation for the email; the invitation
    is marked accepted. The email matching `ADMIN_EMAIL` is exempt and is
    created as an admin. Unless the new account is already verified, a
    verification email is enqueued on the outbox in this same transaction,
    so it is delivered only if the registration commits.
    """
    if await users_service.find_by_email(db, email=payload.email) is not None:
        raise AppError("EMAIL_TAKEN")

    user_payload = UserCreate(
        email=payload.email,
        full_name=payload.full_name,
    )
    password_hash = hash_password(payload.password)

    # The bootstrapped admin registers without an invitation; everyone else
    # needs a pending (unaccepted, unexpired) one.
    is_bootstrap_admin = payload.email == settings.ADMIN_EMAIL
    if is_bootstrap_admin:
        user = await users_service.bootstrap_admin(
            db, payload=user_payload, password_hash=password_hash
        )
    else:
        if not await invitations_service.is_invited(db, email=payload.email):
            raise AppError("INVITATION_REQUIRED")
        user = await users_service.create(
            db, payload=user_payload, password_hash=password_hash
        )

    # The users repository flushed on add, so user.id is assigned below.
    if not is_bootstrap_admin:
        await invitations_service.mark_accepted(
            db, email=payload.email, accepted_by_id=user.id
        )

    # The Redis session is written in-request while the DB transaction commits
    # at request end, so the two are not atomic: a failed commit can leave a
    # short-lived orphan session for a user row that never existed. Acceptable
    # for now — authenticate's user lookup rejects such sessions.
    session_token = await sessions_service.create(redis, user_id=user.id)

    # Enqueued in this transaction, so the verification code is issued and
    # emailed only if the new user's row actually commits.
    if user.email_verified_at is None:
        await outbox_service.enqueue(
            db,
            type=send_verification_email_message.type,
            payload={"user_id": str(user.id)},
            max_attempts=SEND_VERIFICATION_EMAIL_MAX_ATTEMPTS,
        )

    return UserWithSessionToken(user=user, session_token=session_token)


async def authenticate(db: AsyncSession, redis: Redis, *, session_token: str) -> User:
    user_id = await sessions_service.find_user_id(redis, token=session_token)

    if user_id is None:
        raise AppError("INVALID_SESSION")

    user = await users_service.find_by_id(db, user_id=user_id)

    if user is None:
        # The user row is gone (e.g. the account was deleted); the session is
        # dead even if its Redis key still lingers.
        raise AppError("INVALID_SESSION")

    return user


async def logout(redis: Redis, *, session_token: str) -> None:
    await sessions_service.delete_by_token(redis, token=session_token)
