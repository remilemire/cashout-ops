# backend/tests/support/factories.py

"""Helpers for seeding database rows directly (bypassing the API)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.users.model import User
from app.features.users.types import UserRole


async def create_user(
    db: AsyncSession,
    *,
    email: str = "cashier@test.com",
    full_name: str = "Test User",
    role: UserRole = UserRole.STAFF,
) -> User:
    user = User(
        email=email,
        full_name=full_name,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
