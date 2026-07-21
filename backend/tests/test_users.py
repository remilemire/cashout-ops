# backend/tests/test_users.py

from __future__ import annotations

from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from .factories import ADMIN_EMAIL, create_user, csrf_headers


async def test_me_returns_current_user(cashier_client: AsyncClient) -> None:
    response = await cashier_client.get("/api/users/me")

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "cashier@test.com"
    assert "passwordHash" not in body  # never expose the hash
    assert "password" not in body


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/users/me")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


async def test_admin_lists_users(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/api/users")

    assert response.status_code == 200
    body = response.json()
    assert ADMIN_EMAIL in [user["email"] for user in body]
    assert all("passwordHash" not in user for user in body)


async def test_list_users_requires_admin(cashier_client: AsyncClient) -> None:
    response = await cashier_client.get("/api/users")

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
