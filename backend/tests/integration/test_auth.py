from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.redis import Redis
from tests.support.api import login
from tests.support.factories import create_user
from tests.support.fakes import FakeEmailClient
from tests.support.fixtures.outbox import OutboxDrain
from tests.support.fixtures.redis import redis_keys


async def test_logout_clears_session_and_cookies(
    client: AsyncClient,
    db_session: AsyncSession,
    redis_client: Redis,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    await create_user(db_session, email="out@test.com")
    await login(
        client,
        email="out@test.com",
        drain_outbox=drain_outbox,
        email_client=email_client,
    )
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
