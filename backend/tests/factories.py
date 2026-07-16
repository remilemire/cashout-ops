# backend/tests/factories.py

"""Helpers for seeding data and driving the authenticated API in tests."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.auth.passwords import hash_password
from app.features.users.model import User
from app.features.users.types import UserRole

# Matches ADMIN_EMAIL set in conftest; register() promotes this email to ADMIN.
ADMIN_EMAIL = "admin@test.com"
DEFAULT_PASSWORD = "password123"


async def create_user(
    db: AsyncSession,
    *,
    email: str = "cashier@test.com",
    password: str = DEFAULT_PASSWORD,
    role: UserRole = UserRole.CASHIER,
    first_name: str = "Test",
    last_name: str = "User",
) -> User:
    user = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


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
    first_name: str = "Test",
    last_name: str = "User",
) -> None:
    """Register through the API; the client then carries session + csrf cookies."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "password": password,
        },
    )
    assert response.status_code == 200, response.text


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
