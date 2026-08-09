# backend/tests/support/factories.py

"""Helpers for seeding database rows directly (bypassing the API)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.users.model import User


async def create_user(
    db: AsyncSession,
    *,
    email: str = "cashier@test.com",
    full_name: str = "Test User",
    is_admin: bool = False,
    verified: bool = True,
) -> User:
    user = User(
        email=email,
        full_name=full_name,
        is_admin=is_admin,
        # Temporary until the next increment removes email verification: most
        # protected routes are guarded by require_verified_user, so seeded
        # users arrive verified unless a test opts out.
        email_verified_at=datetime.now(UTC) if verified else None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
