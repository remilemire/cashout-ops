# backend/tests/test_auth.py

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.sessions.model import Session
from app.features.users.types import UserRole

from .factories import ADMIN_EMAIL, csrf_headers, register


async def test_register_creates_user_and_sets_cookies(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "new@test.com",
            "firstName": "New",
            "lastName": "User",
            "password": "password123",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@test.com"
    assert body["role"] == UserRole.CASHIER.value
    # Inbound/outbound JSON is camelCase.
    assert body["firstName"] == "New"
    assert "session_token" in client.cookies
    assert "csrf_token" in client.cookies


async def test_register_promotes_admin_email(client: AsyncClient) -> None:
    await register(client, email=ADMIN_EMAIL)

    response = await client.get("/api/users/me")
    assert response.json()["role"] == UserRole.ADMIN.value


async def test_register_duplicate_email_conflicts(client: AsyncClient) -> None:
    await register(client, email="dupe@test.com")

    response = await client.post(
        "/api/auth/register",
        json={
            "email": "dupe@test.com",
            "firstName": "Other",
            "lastName": "Person",
            "password": "password123",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ALREADY_EXISTS"


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "short@test.com",
            "firstName": "Short",
            "lastName": "Pass",
            "password": "x",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "UNPROCESSABLE"
    assert body["errors"][0]["path"] == ["password"]


async def test_login_succeeds_with_correct_password(client: AsyncClient) -> None:
    await register(client, email="login@test.com", password="password123")
    client.cookies.clear()

    response = await client.post(
        "/api/auth/login",
        json={"email": "login@test.com", "password": "password123"},
    )

    assert response.status_code == 200
    assert "session_token" in client.cookies


async def test_login_wrong_password_unauthorized(client: AsyncClient) -> None:
    await register(client, email="wrong@test.com", password="password123")

    response = await client.post(
        "/api/auth/login",
        json={"email": "wrong@test.com", "password": "not-the-password"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_login_unknown_email_unauthorized(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"email": "nobody@test.com", "password": "password123"},
    )

    assert response.status_code == 401


async def test_logout_clears_session_and_cookies(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(client, email="out@test.com")
    assert (await db_session.execute(select(Session))).scalars().all()

    response = await client.post("/api/auth/logout", headers=csrf_headers(client))

    assert response.status_code == 204
    # Cookies cleared, and the session row is deleted.
    assert not client.cookies.get("session_token")
    assert (await db_session.execute(select(Session))).scalars().all() == []


async def test_logout_requires_csrf(client: AsyncClient) -> None:
    await register(client, email="csrf@test.com")

    # No x-csrf-token header → rejected by the double-submit check.
    response = await client.post("/api/auth/logout")

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
