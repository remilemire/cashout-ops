# backend/tests/support/factories.py

"""Helpers for seeding database rows directly (bypassing the API)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.auth.passwords import hash_password
from app.features.invitations.model import Invitation
from app.features.users.model import User

from .api import DEFAULT_PASSWORD


async def create_user(
    db: AsyncSession,
    *,
    email: str = "cashier@test.com",
    password: str = DEFAULT_PASSWORD,
    is_admin: bool = False,
    full_name: str = "Test User",
) -> User:
    user = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        is_admin=is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def create_invitation(
    db: AsyncSession,
    *,
    email: str,
    expires_at: datetime | None = None,
) -> Invitation:
    """Seed an invitation (and its inviter) so register() succeeds for email."""
    inviter = User(
        email=f"inviter-{uuid.uuid4().hex[:8]}@test.com",
        full_name="Inviting Admin",
        password_hash="!",  # never logs in; skip the slow bcrypt hash
        is_admin=True,
    )
    db.add(inviter)
    await db.flush()

    invitation = Invitation(
        email=email,
        invited_by_user_id=inviter.id,
        expires_at=expires_at or datetime.now(UTC) + timedelta(days=7),
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    return invitation


async def verify_user(db: AsyncSession, *, email: str) -> None:
    """Mark a registered user's email verified (bypasses the emailed code).

    Most protected routes are guarded by require_verified_user, so client
    fixtures verify after registering.
    """
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    user.email_verified_at = datetime.now(UTC)
    await db.commit()
