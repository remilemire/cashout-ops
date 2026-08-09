# backend/tests/integration/test_users.py

from __future__ import annotations

from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.auth.email_verification import service as email_verification_service
from app.features.users import service as users_service
from app.infrastructure.redis import Redis
from tests.support.api import ADMIN_EMAIL, csrf_headers, login
from tests.support.factories import create_user
from tests.support.fakes import FakeEmailClient
from tests.support.fixtures.outbox import OutboxDrain
from tests.support.fixtures.redis import redis_keys


async def test_me_returns_current_user(cashier_client: AsyncClient) -> None:
    response = await cashier_client.get("/api/users/me")

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "cashier@test.com"


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/users/me")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


async def test_admin_lists_users(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/api/users")

    assert response.status_code == 200
    body = response.json()
    assert ADMIN_EMAIL in [user["email"] for user in body]


async def test_list_users_requires_admin(cashier_client: AsyncClient) -> None:
    response = await cashier_client.get("/api/users")

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_admin_creates_user(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        "/api/users",
        json={"email": "new@test.com", "fullName": "New Staff"},
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "new@test.com"
    # Inbound/outbound JSON is camelCase.
    assert body["fullName"] == "New Staff"
    assert body["isAdmin"] is False
    # Creating an account signs nobody in: no auth cookies on the response.
    assert "session_token" not in response.cookies
    assert "csrf_token" not in response.cookies


async def test_created_user_can_sign_in(
    admin_client: AsyncClient,
    client: AsyncClient,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    created = await admin_client.post(
        "/api/users",
        json={"email": "staff@test.com", "fullName": "New Staff"},
        headers=csrf_headers(admin_client),
    )
    assert created.status_code == 201, created.text

    await login(
        client,
        email="staff@test.com",
        drain_outbox=drain_outbox,
        email_client=email_client,
    )

    assert (await client.get("/api/users/me")).status_code == 200


async def test_create_user_duplicate_email_conflicts(
    admin_client: AsyncClient,
) -> None:
    first = await admin_client.post(
        "/api/users",
        json={"email": "dupe@test.com", "fullName": "First Staff"},
        headers=csrf_headers(admin_client),
    )
    assert first.status_code == 201, first.text

    response = await admin_client.post(
        "/api/users",
        json={"email": "dupe@test.com", "fullName": "Second Staff"},
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "EMAIL_TAKEN"


async def test_create_user_requires_admin(cashier_client: AsyncClient) -> None:
    response = await cashier_client.post(
        "/api/users",
        json={"email": "new@test.com", "fullName": "New Staff"},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_admin_promotes_user(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, email="staff@test.com")

    response = await admin_client.post(
        f"/api/users/{user.id}/promote", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["isAdmin"] is True


async def test_admin_demotes_user(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, email="other@test.com", is_admin=True)

    response = await admin_client.post(
        f"/api/users/{user.id}/demote", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["isAdmin"] is False


async def test_promote_requires_admin(
    cashier_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, email="staff@test.com")

    response = await cashier_client.post(
        f"/api/users/{user.id}/promote", headers=csrf_headers(cashier_client)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_demote_requires_admin(
    cashier_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, email="staff@test.com", is_admin=True)

    response = await cashier_client.post(
        f"/api/users/{user.id}/demote", headers=csrf_headers(cashier_client)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_admin_cannot_promote_self(admin_client: AsyncClient) -> None:
    me = (await admin_client.get("/api/users/me")).json()

    response = await admin_client.post(
        f"/api/users/{me['id']}/promote", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CANNOT_MODIFY_OWN_ADMIN"


async def test_admin_cannot_demote_self(admin_client: AsyncClient) -> None:
    me = (await admin_client.get("/api/users/me")).json()
    assert me["isAdmin"] is True  # self-demotion is the realistic lockout risk

    response = await admin_client.post(
        f"/api/users/{me['id']}/demote", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CANNOT_MODIFY_OWN_ADMIN"


async def test_promote_unknown_user_not_found(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        f"/api/users/{uuid4()}/promote", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "USER_NOT_FOUND"


async def test_demote_unknown_user_not_found(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        f"/api/users/{uuid4()}/demote", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "USER_NOT_FOUND"


async def test_deleting_user_revokes_their_sessions_and_verification_code(
    client: AsyncClient,
    db_session: AsyncSession,
    db_sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Seeded directly (unverified, so a verification code can be issued below),
    # then logged in through the API for a real session. No HTTP route deletes
    # users yet, so the deletion goes through the service; the revocation is
    # still observed through the deleted user's previously-valid client.
    user = await create_user(db_session, email="doomed@test.com", verified=False)
    await login(
        client,
        email="doomed@test.com",
        drain_outbox=drain_outbox,
        email_client=email_client,
    )
    assert (await client.get("/api/users/me")).status_code == 200
    assert await redis_keys(redis_client, "session:*")

    # Give the (unverified) user an outstanding verification code the same way
    # the resend outbox job would.
    await email_verification_service.send_new_code(
        db_sessionmaker, redis_client, email_client=email_client, user_id=user.id
    )
    assert await redis_keys(redis_client, "email_verification:*")

    await users_service.delete_by_id(db_session, redis_client, user_id=user.id)
    await db_session.commit()

    response = await client.get("/api/users/me")
    assert response.status_code == 401
    assert await redis_keys(redis_client, "session:*") == []
    assert await redis_keys(redis_client, "user_sessions:*") == []
    assert await redis_keys(redis_client, "email_verification:*") == []
