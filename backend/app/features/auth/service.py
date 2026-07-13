# backend/app/features/auth/service.py

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import AlreadyExistsError, UnauthorizedError
from app.features.sessions import service as sessions_service
from app.features.users import service as users_service
from app.features.users.schemas import UserCreate
from app.features.users.types import UserRole

from .passwords import hash_password, verify_password
from .schemas import AuthLogin, AuthRegister
from .types import AuthContext, UserWithSessionToken


async def login(db: AsyncSession, *, payload: AuthLogin) -> UserWithSessionToken:
    user = await users_service.find_by_email(db, email=payload.email)

    if user is None:
        raise UnauthorizedError("Incorrect email or password.")

    if not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Incorrect email or password.")

    result = sessions_service.create(db, user_id=user.id)
    return UserWithSessionToken(user=user, session_token=result.session_token)


async def register(db: AsyncSession, *, payload: AuthRegister) -> UserWithSessionToken:
    if await users_service.find_by_email(db, email=payload.email) is not None:
        raise AlreadyExistsError("A user with this email already exists.")

    role = UserRole.ADMIN if payload.email == settings.ADMIN_EMAIL else None
    user = users_service.create(
        db,
        payload=UserCreate(
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
        ),
        password_hash=hash_password(payload.password),
        role=role,
    )

    # Flush so the new user's PK is available for the session FK.
    await db.flush()

    result = sessions_service.create(db, user_id=user.id)
    return UserWithSessionToken(user, result.session_token)


async def authenticate(db: AsyncSession, *, session_token: str) -> AuthContext:
    session = await sessions_service.find_valid_with_user(db, token=session_token)

    if session is None:
        raise UnauthorizedError("Invalid or expired session.")

    return AuthContext(user=session.user, session=session)


async def logout(db: AsyncSession, *, session_token: str) -> None:
    await sessions_service.delete_by_token(db, token=session_token)
