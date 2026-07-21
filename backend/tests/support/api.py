# backend/tests/support/api.py

"""Drivers for the authentication API and CSRF handling in tests."""

from __future__ import annotations

from httpx import AsyncClient

# Matches ADMIN_EMAIL set in conftest; register() promotes this email to ADMIN.
ADMIN_EMAIL = "admin@test.com"
DEFAULT_PASSWORD = "password123"


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
