# backend/app/features/users/service.py

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError

from .model import User
from .schemas import UserCreate


async def list_users(db: AsyncSession) -> Sequence[User]:
    """Every user, newest first (admin table)."""
    stmt = select(User).order_by(User.created_at.desc())
    return (await db.execute(stmt)).scalars().all()


async def find_by_email(db: AsyncSession, *, email: str) -> User | None:
    stmt = select(User).where(User.email == email)

    user = (await db.execute(stmt)).scalar_one_or_none()

    return user


def create(db: AsyncSession, *, payload: UserCreate, password_hash: str) -> User:
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=password_hash,
    )
    db.add(user)

    return user


def bootstrap_admin(
    db: AsyncSession, *, payload: UserCreate, password_hash: str
) -> User:
    """Create the bootstrapped ADMIN_EMAIL account as an admin."""
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        is_admin=True,
        password_hash=password_hash,
    )
    db.add(user)

    return user


async def delete_by_id(db: AsyncSession, *, user_id: UUID) -> None:
    user = await User.find_by_id(db, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND")
    await db.delete(user)


async def promote_admin(db: AsyncSession, *, user_id: UUID, actor: User) -> User:
    """Grant a user admin access (idempotent if already an admin).

    An admin cannot change their own admin access.
    """
    if actor.id == user_id:
        raise AppError("CANNOT_MODIFY_OWN_ADMIN")
    user = await User.find_by_id(db, user_id)
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
    user = await User.find_by_id(db, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND")
    user.is_admin = False
    return user


__all__ = [
    "list_users",
    "find_by_email",
    "create",
    "bootstrap_admin",
    "delete_by_id",
    "promote_admin",
    "demote_admin",
]
