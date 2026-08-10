# backend/app/features/users/repository.py

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .model import User


async def list_all(db: AsyncSession) -> Sequence[User]:
    stmt = select(User).order_by(User.created_at.desc())
    return (await db.execute(stmt)).scalars().all()


async def find_by_email(db: AsyncSession, *, email: str) -> User | None:
    stmt = select(User).where(User.email == email)

    user = (await db.execute(stmt)).scalar_one_or_none()

    return user


async def find_by_id(db: AsyncSession, *, user_id: UUID) -> User | None:
    return await db.get(User, user_id)


async def add(db: AsyncSession, user: User) -> None:
    """Stage the user and flush so its generated PK is assigned."""
    db.add(user)
    await db.flush()


async def delete(db: AsyncSession, user: User) -> None:
    await db.delete(user)


async def flush(db: AsyncSession) -> None:
    """Push pending changes to the database without committing.

    Flush placement is behavior: it controls when constraint violations
    surface (e.g. ordering the two role UPDATEs of an ownership transfer).
    """
    await db.flush()


__all__ = ["list_all", "find_by_email", "find_by_id", "add", "delete", "flush"]
