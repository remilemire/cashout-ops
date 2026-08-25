# backend/app/features/users/repository.py

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .model import User
from .types import UserRole

# Soft-deleted rows (deleted_at set) behave as gone: every live-account
# lookup below excludes them. Only find_by_email_include_deleted sees them,
# for the reinvite flow.


async def list_all(db: AsyncSession) -> Sequence[User]:
    stmt = (
        select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.desc())
    )
    return (await db.execute(stmt)).scalars().all()


async def find_by_email(db: AsyncSession, *, email: str) -> User | None:
    stmt = select(User).where(User.email == email, User.deleted_at.is_(None))

    user = (await db.execute(stmt)).scalar_one_or_none()

    return user


async def find_by_email_include_deleted(db: AsyncSession, *, email: str) -> User | None:
    """The email's row even when soft-deleted (ix_users_email spans both).

    Only the reinvite path in the users service should need this; everything
    else treats a soft-deleted account as nonexistent.
    """
    stmt = select(User).where(User.email == email)

    return (await db.execute(stmt)).scalar_one_or_none()


async def find_by_id(db: AsyncSession, *, user_id: UUID) -> User | None:
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))

    return (await db.execute(stmt)).scalar_one_or_none()


async def owner_exists(db: AsyncSession) -> bool:
    """Whether any account currently holds the owner role.

    ix_users_single_owner indexes exactly these rows, so this is an
    index-only probe rather than a scan of the table.
    """
    stmt = select(select(User.id).where(User.role == UserRole.OWNER).exists())

    return bool((await db.execute(stmt)).scalar())


async def add(db: AsyncSession, user: User) -> None:
    """Stage the user and flush so its generated PK is assigned."""
    db.add(user)
    await db.flush()


async def add_if_unique(db: AsyncSession, user: User) -> bool:
    """Stage the user and flush, reporting whether the insert took.

    The SAVEPOINT is what makes a lost race survivable: a violation of
    ix_users_email or ix_users_single_owner would otherwise poison the whole
    request transaction, leaving the caller a session it can no longer commit
    even though it handled the loss.
    """
    try:
        async with db.begin_nested():
            db.add(user)
            await db.flush()
    except IntegrityError:
        return False

    return True


async def delete(db: AsyncSession, user: User) -> None:
    await db.delete(user)
    # Flush so an unexpected FK violation (e.g. a submission created in a race
    # with the has-submissions check) surfaces inside the request — where the
    # IntegrityError translator turns it into a 409 — instead of at commit
    # time in get_db's teardown, after the 204 was already sent.
    await db.flush()


async def flush(db: AsyncSession) -> None:
    """Push pending changes to the database without committing.

    Flush placement is behavior: it controls when constraint violations
    surface (e.g. ordering the two role UPDATEs of an ownership transfer).
    """
    await db.flush()


__all__ = [
    "list_all",
    "find_by_email",
    "find_by_email_include_deleted",
    "find_by_id",
    "owner_exists",
    "add",
    "add_if_unique",
    "delete",
    "flush",
]
