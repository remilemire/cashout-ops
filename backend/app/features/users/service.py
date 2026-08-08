# backend/app/features/users/service.py

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.features.auth.email_verification import service as email_verification_service
from app.features.auth.sessions import service as sessions_service
from app.infrastructure.redis import Redis

from . import repository
from .model import User
from .schemas import UserCreate


async def list_users(db: AsyncSession) -> Sequence[User]:
    """Every user, newest first (admin table)."""
    return await repository.list_all(db)


async def find_by_email(db: AsyncSession, *, email: str) -> User | None:
    return await repository.find_by_email(db, email=email)


async def find_by_id(db: AsyncSession, *, user_id: UUID) -> User | None:
    return await repository.find_by_id(db, user_id=user_id)


async def create(db: AsyncSession, *, payload: UserCreate, password_hash: str) -> User:
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=password_hash,
    )
    await repository.add(db, user)

    return user


async def bootstrap_admin(
    db: AsyncSession, *, payload: UserCreate, password_hash: str
) -> User:
    """Create the bootstrapped ADMIN_EMAIL account as an admin."""
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        is_admin=True,
        password_hash=password_hash,
    )
    await repository.add(db, user)

    return user


async def delete_by_id(db: AsyncSession, redis: Redis, *, user_id: UUID) -> None:
    user = await repository.find_by_id(db, user_id=user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND")
    await repository.delete(db, user)
    # Best-effort session revocation and verification-code cleanup (the old
    # FK cascade): not atomic with the transaction (the planned transactional
    # outbox will make it so). If the Redis write is lost, authenticate's
    # failed user lookup remains the backstop for sessions, and an orphaned
    # verification code expires with its TTL.
    await sessions_service.delete_all_for_user(redis, user_id=user_id)
    await email_verification_service.delete_for_user(redis, user_id=user_id)


async def promote_admin(db: AsyncSession, *, user_id: UUID, actor: User) -> User:
    """Grant a user admin access (idempotent if already an admin).

    An admin cannot change their own admin access.
    """
    if actor.id == user_id:
        raise AppError("CANNOT_MODIFY_OWN_ADMIN")
    user = await repository.find_by_id(db, user_id=user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND")
    user.is_admin = True
    return user


async def demote_admin(db: AsyncSession, *, user_id: UUID, actor: User) -> User:
    """Revoke a user's admin access (idempotent if already staff).

    An admin cannot change their own admin access.
    """
    if actor.id == user_id:
        raise AppError("CANNOT_MODIFY_OWN_ADMIN")
    user = await repository.find_by_id(db, user_id=user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND")
    user.is_admin = False
    return user


__all__ = [
    "list_users",
    "find_by_email",
    "find_by_id",
    "create",
    "bootstrap_admin",
    "delete_by_id",
    "promote_admin",
    "demote_admin",
]
