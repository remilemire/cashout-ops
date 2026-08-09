# backend/tests/support/factories.py

"""Helpers for seeding database rows directly (bypassing the API)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.users.model import User


async def create_user(
    db: AsyncSession,
    *,
    email: str = "cashier@test.com",
    full_name: str = "Test User",
    is_admin: bool = False,
) -> User:
    user = User(
        email=email,
        full_name=full_name,
        is_admin=is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
