# backend/tests/test_users.py

from __future__ import annotations

from httpx import AsyncClient

from .factories import ADMIN_EMAIL


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
