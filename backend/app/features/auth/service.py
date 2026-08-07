# backend/app/features/auth/service.py

from __future__ import annotations

from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.dependencies.background import PostCommitTasks
from app.errors import AppError
from app.features.invitations import service as invitations_service
from app.features.users import service as users_service
from app.features.users.model import User
from app.features.users.schemas import UserCreate
from app.infrastructure.redis import Redis
from app.integrations.email import EmailClient
from app.security.passwords import hash_password, verify_password

from .email_verification import service as email_verification_service
from .schemas import AuthLogin, AuthRegister
from .sessions import service as sessions_service
from .types import UserWithSessionToken


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
    post_commit: PostCommitTasks,
    sessionmaker: async_sessionmaker[AsyncSession],
    email_client: EmailClient,
) -> UserWithSessionToken:
    """Create an account, start a session, and queue a verification email.

    Registration requires a pending invitation for the email; the invitation
    is marked accepted. The email matching `ADMIN_EMAIL` is exempt and is
    created as an admin. Unless the new account is already verified, a
    verification code is queued to be emailed after the request commits.
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
        user = users_service.bootstrap_admin(
            db, payload=user_payload, password_hash=password_hash
        )
    else:
        if not await invitations_service.is_invited(db, email=payload.email):
            raise AppError("INVITATION_REQUIRED")
        user = users_service.create(
            db, payload=user_payload, password_hash=password_hash
        )

    # Flush so the new user's PK is assigned before it is referenced below.
    await db.flush()

    if not is_bootstrap_admin:
        await invitations_service.mark_accepted(
            db, email=payload.email, accepted_by_id=user.id
        )

    # The Redis session is written in-request while the DB transaction commits
    # at request end, so the two are not atomic: a failed commit can leave a
    # short-lived orphan session for a user row that never existed. Acceptable
    # for now — authenticate's user lookup rejects such sessions.
    session_token = await sessions_service.create(redis, user_id=user.id)

    # Queued so the verification code is issued + emailed only once the new
    # user is persisted (the job runs after the request transaction commits).
    if user.email_verified_at is None:
        post_commit.add(
            partial(
                email_verification_service.send_new_code,
                sessionmaker,
                email_client=email_client,
                user_id=user.id,
            )
        )

    return UserWithSessionToken(user=user, session_token=session_token)


async def authenticate(db: AsyncSession, redis: Redis, *, session_token: str) -> User:
    user_id = await sessions_service.find_user_id(redis, token=session_token)

    if user_id is None:
        raise AppError("INVALID_SESSION")

    user = await db.get(User, user_id)

    if user is None:
        # The user row is gone (e.g. the account was deleted); the session is
        # dead even if its Redis key still lingers.
        raise AppError("INVALID_SESSION")

    return user


async def logout(redis: Redis, *, session_token: str) -> None:
    await sessions_service.delete_by_token(redis, token=session_token)
