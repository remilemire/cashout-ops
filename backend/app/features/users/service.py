# backend/app/features/users/service.py

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError

from . import repository
from .model import User
from .schemas import UserCreate, UserUpdate
from .types import UserRole


async def list_users(db: AsyncSession) -> Sequence[User]:
    """Every user, newest first (admin table)."""
    return await repository.list_all(db)


async def find_by_email(db: AsyncSession, *, email: str) -> User | None:
    return await repository.find_by_email(db, email=email)


async def find_by_id(db: AsyncSession, *, user_id: UUID) -> User | None:
    return await repository.find_by_id(db, user_id=user_id)


async def create(db: AsyncSession, *, payload: UserCreate) -> User:
    user = User(
        email=payload.email,
        full_name=payload.full_name,
    )
    await repository.add(db, user)

    return user


async def update(db: AsyncSession, *, user_id: UUID, payload: UserUpdate) -> User:
    """Update a user's profile details.

    Renaming is not a privilege change, so it is allowed on any account —
    including the owner's and the caller's own.
    """
    user = await repository.find_by_id(db, user_id=user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND")
    user.full_name = payload.full_name
    return user


async def bootstrap_owner(db: AsyncSession, *, payload: UserCreate) -> User:
    """Create the bootstrapped BOOTSTRAP_OWNER_EMAIL account as the owner."""
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        role=UserRole.OWNER,
    )
    await repository.add(db, user)

    return user


async def delete_by_id(db: AsyncSession, *, user_id: UUID) -> None:
    user = await repository.find_by_id(db, user_id=user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND")
    if user.role is UserRole.OWNER:
        raise AppError("CANNOT_DELETE_OWNER")
    await repository.delete(db, user)


async def promote_admin(db: AsyncSession, *, user_id: UUID, actor: User) -> User:
    """Grant a user admin access (idempotent if already an admin).

    An admin cannot change their own admin access, and the owner's role
    cannot be changed.
    """
    if actor.id == user_id:
        raise AppError("CANNOT_MODIFY_OWN_ADMIN")
    user = await repository.find_by_id(db, user_id=user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND")
    if user.role is UserRole.OWNER:
        raise AppError("CANNOT_MODIFY_OWNER")
    user.role = UserRole.ADMIN
    return user


async def demote_admin(db: AsyncSession, *, user_id: UUID, actor: User) -> User:
    """Revoke a user's admin access (idempotent if already staff).

    An admin cannot change their own admin access, and the owner's role
    cannot be changed.
    """
    if actor.id == user_id:
        raise AppError("CANNOT_MODIFY_OWN_ADMIN")
    user = await repository.find_by_id(db, user_id=user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND")
    if user.role is UserRole.OWNER:
        raise AppError("CANNOT_MODIFY_OWNER")
    user.role = UserRole.STAFF
    return user


async def transfer_ownership(
    db: AsyncSession, *, actor: User, new_owner_id: UUID
) -> User:
    """Transfer the actor's ownership to an admin, returning the new owner.

    The actor is required here because the operation logically transfers THEIR
    ownership (the require_owner dependency guarantees they hold it). Only an
    admin can receive it — this also rejects the actor targeting themselves.

    The demotion is flushed before the promotion: within a single flush the
    UPDATE order is unspecified, so ix_users_single_owner could see two owners
    mid-flight and reject a legitimate transfer.
    """
    user = await repository.find_by_id(db, user_id=new_owner_id)
    if user is None:
        raise AppError("USER_NOT_FOUND")
    if user.role is not UserRole.ADMIN:
        raise AppError("TRANSFER_TARGET_NOT_ADMIN")
    actor.role = UserRole.ADMIN
    await repository.flush(db)
    user.role = UserRole.OWNER
    await repository.flush(db)
    return user


__all__ = [
    "list_users",
    "find_by_email",
    "find_by_id",
    "create",
    "update",
    "bootstrap_owner",
    "delete_by_id",
    "promote_admin",
    "demote_admin",
    "transfer_ownership",
]
