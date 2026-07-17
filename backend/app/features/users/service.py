# backend/app/features/users/service.py

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .model import User
from .schemas import UserCreate
from .types import UserRole


async def find_by_email(db: AsyncSession, *, email: str) -> User | None:
    stmt = select(User).where(User.email == email)

    user = (await db.execute(stmt)).scalar_one_or_none()

    return user


def create(
    db: AsyncSession,
    *,
    payload: UserCreate,
    password_hash: str,
    role: UserRole | None = None,
) -> User:
    user = User(
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        role=role,
        password_hash=password_hash,
    )
    db.add(user)

    return user


async def delete_by_id(db: AsyncSession, *, user_id: UUID) -> None:
    user = await User.get_active(db, user_id)
    await db.delete(user)


__all__ = ["find_by_email", "create", "delete_by_id"]
