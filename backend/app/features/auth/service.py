# backend/app/features/auth/service.py

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import AppError
from app.features.invitations import service as invitations_service
from app.features.sessions import service as sessions_service
from app.features.users import service as users_service
from app.features.users.schemas import UserCreate

from .passwords import hash_password, verify_password
from .schemas import AuthLogin, AuthRegister
from .types import AuthContext, UserWithSessionToken


async def login(db: AsyncSession, *, payload: AuthLogin) -> UserWithSessionToken:
    user = await users_service.find_by_email(db, email=payload.email)

    if user is None:
        raise AppError("INVALID_CREDENTIALS")

    if not verify_password(payload.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS")

    result = sessions_service.create(db, user_id=user.id)
    return UserWithSessionToken(user=user, session_token=result.session_token)


async def register(db: AsyncSession, *, payload: AuthRegister) -> UserWithSessionToken:
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

    # Flush so the new user's PK is available for the session FK.
    await db.flush()

    if not is_bootstrap_admin:
        await invitations_service.mark_accepted(
            db, email=payload.email, accepted_by_id=user.id
        )

    result = sessions_service.create(db, user_id=user.id)
    return UserWithSessionToken(user, result.session_token)


async def authenticate(db: AsyncSession, *, session_token: str) -> AuthContext:
    session = await sessions_service.find_valid_with_user(db, token=session_token)

    if session is None:
        raise AppError("INVALID_SESSION")

    return AuthContext(user=session.user, session=session)


async def logout(db: AsyncSession, *, session_token: str) -> None:
    await sessions_service.delete_by_token(db, token=session_token)
