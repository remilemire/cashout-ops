# backend/tests/integration/test_auth.py

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.redis import Redis
from tests.support.api import ADMIN_EMAIL, register
from tests.support.factories import create_invitation
from tests.support.fixtures.redis import redis_keys


async def test_register_creates_user_and_sets_cookies(
    client: AsyncClient, db_session: AsyncSession, redis_client: Redis
) -> None:
    await create_invitation(db_session, email="new@test.com")

    response = await client.post(
        "/api/auth/register",
        json={
            "email": "new@test.com",
            "fullName": "New User",
            "password": "password123",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@test.com"
    assert body["isAdmin"] is False
    # Inbound/outbound JSON is camelCase.
    assert body["fullName"] == "New User"
    assert "session_token" in client.cookies
    assert "csrf_token" in client.cookies
    # The session is tracked in Redis (keyed by the token's hash).
    assert await redis_keys(redis_client, "session:*")


async def test_register_promotes_admin_email(client: AsyncClient) -> None:
    await register(client, email=ADMIN_EMAIL)

    response = await client.get("/api/users/me")
    assert response.json()["isAdmin"] is True


async def test_register_duplicate_email_conflicts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_invitation(db_session, email="dupe@test.com")
    await register(client, email="dupe@test.com")

    response = await client.post(
        "/api/auth/register",
        json={
            "email": "dupe@test.com",
            "fullName": "Other Person",
            "password": "password123",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "EMAIL_TAKEN"


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "short@test.com",
            "fullName": "Short Pass",
            "password": "x",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["kind"] == "VALIDATION"
    assert body["issues"][0]["path"] == ["password"]


async def test_login_succeeds_with_correct_password(
    client: AsyncClient, db_session: AsyncSession, redis_client: Redis
) -> None:
    await create_invitation(db_session, email="login@test.com")
    await register(client, email="login@test.com", password="password123")
    client.cookies.clear()
    # Drop the registration session so the assertion sees only login's.
    await redis_client.flushdb()  # pyright: ignore[reportUnknownMemberType]

    response = await client.post(
        "/api/auth/login",
        json={"email": "login@test.com", "password": "password123"},
    )

    assert response.status_code == 200
    assert "session_token" in client.cookies
    # Login minted a fresh Redis-tracked session.
    assert await redis_keys(redis_client, "session:*")


async def test_login_wrong_password_unauthorized(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_invitation(db_session, email="wrong@test.com")
    await register(client, email="wrong@test.com", password="password123")

    response = await client.post(
        "/api/auth/login",
        json={"email": "wrong@test.com", "password": "not-the-password"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


async def test_login_unknown_email_unauthorized(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"email": "nobody@test.com", "password": "password123"},
    )

    assert response.status_code == 401


async def test_logout_clears_session_and_cookies(
    client: AsyncClient, db_session: AsyncSession, redis_client: Redis
) -> None:
    await create_invitation(db_session, email="out@test.com")
    await register(client, email="out@test.com")
    session_token = client.cookies["session_token"]
    assert await redis_keys(redis_client, "session:*")

    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
    # Cookies cleared, and the Redis session key is deleted.
    assert not client.cookies.get("session_token")
    assert await redis_keys(redis_client, "session:*") == []
    # The session is revoked server-side: replaying the old token fails.
    client.cookies.set("session_token", session_token)
    assert (await client.get("/api/users/me")).status_code == 401


async def test_logout_with_invalid_session_returns_204(client: AsyncClient) -> None:
    # Logout requires neither auth nor CSRF: a missing or already-invalid
    # session still clears the cookies and returns 204 rather than erroring.
    client.cookies.set("session_token", "not-a-real-token")

    response = await client.post("/api/auth/logout")

    assert response.status_code == 204
