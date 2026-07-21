# backend/tests/factories.py

"""Helpers for seeding data and driving the authenticated API in tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.auth.passwords import hash_password
from app.features.invitations.model import Invitation
from app.features.users.model import User

# Matches ADMIN_EMAIL set in conftest; register() promotes this email to ADMIN.
ADMIN_EMAIL = "admin@test.com"
DEFAULT_PASSWORD = "password123"


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


def csrf_headers(client: AsyncClient) -> dict[str, str]:
    """The x-csrf-token header matching the readable csrf cookie, for unsafe methods."""
    token = client.cookies.get("csrf_token")
    assert token is not None, "no csrf cookie set; log in first"
    return {"x-csrf-token": token}


async def register(
    client: AsyncClient,
    *,
    email: str = "cashier@test.com",
    password: str = DEFAULT_PASSWORD,
    full_name: str = "Test User",
) -> None:
    """Register through the API; the client then carries session + csrf cookies.

    The email must hold a pending invitation (see create_invitation) unless it
    is ADMIN_EMAIL, which registers without one.
    """
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "fullName": full_name,
            "password": password,
        },
    )
    assert response.status_code == 201, response.text


async def login(
    client: AsyncClient,
    *,
    email: str = "cashier@test.com",
    password: str = DEFAULT_PASSWORD,
) -> None:
    response = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
