# backend/tests/test_invitations.py

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.invitations.model import Invitation

from .factories import create_invitation, create_user, csrf_headers, register

# ================================
# --------- Registration ---------
# ================================


async def test_register_without_invitation_forbidden(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "uninvited@test.com",
            "firstName": "No",
            "lastName": "Invite",
            "password": "password123",
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "INVITATION_REQUIRED"


async def test_register_with_expired_invitation_forbidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_invitation(
        db_session,
        email="late@test.com",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )

    response = await client.post(
        "/api/auth/register",
        json={
            "email": "late@test.com",
            "firstName": "Too",
            "lastName": "Late",
            "password": "password123",
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "INVITATION_REQUIRED"


async def test_register_marks_invitation_accepted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_invitation(db_session, email="invited@test.com")

    await register(client, email="invited@test.com")

    me = await client.get("/api/users/me")
    stmt = select(Invitation).where(Invitation.email == "invited@test.com")
    invitation = (await db_session.execute(stmt)).scalar_one()
    assert invitation.accepted_at is not None
    assert str(invitation.accepted_by_user_id) == me.json()["id"]


# ================================
# ---------- Endpoints -----------
# ================================


async def test_create_and_list_invitations(admin_client: AsyncClient) -> None:
    created = await admin_client.post(
        "/api/invitations",
        json={"email": "newhire@test.com"},
        headers=csrf_headers(admin_client),
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] == "newhire@test.com"
    assert body["acceptedAt"] is None
    assert body["acceptedByUserId"] is None
    admin = (await admin_client.get("/api/users/me")).json()
    assert body["invitedByUserId"] == admin["id"]

    listed = await admin_client.get("/api/invitations")
    assert listed.status_code == 200
    assert [invitation["id"] for invitation in listed.json()] == [body["id"]]


async def test_create_duplicate_invitation_conflicts(
    admin_client: AsyncClient,
) -> None:
    headers = csrf_headers(admin_client)
    payload = {"email": "twice@test.com"}
    assert (
        await admin_client.post("/api/invitations", json=payload, headers=headers)
    ).status_code == 201

    response = await admin_client.post(
        "/api/invitations", json=payload, headers=headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "INVITATION_EXISTS"


async def test_create_invitation_for_registered_email_conflicts(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_user(db_session, email="already@test.com")

    response = await admin_client.post(
        "/api/invitations",
        json={"email": "already@test.com"},
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "EMAIL_TAKEN"


async def test_delete_invitation(admin_client: AsyncClient) -> None:
    created = await admin_client.post(
        "/api/invitations",
        json={"email": "revoked@test.com"},
        headers=csrf_headers(admin_client),
    )

    response = await admin_client.delete(
        f"/api/invitations/{created.json()['id']}",
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 204
    assert (await admin_client.get("/api/invitations")).json() == []


async def test_delete_missing_invitation_not_found(admin_client: AsyncClient) -> None:
    response = await admin_client.delete(
        f"/api/invitations/{uuid4()}", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "INVITATION_NOT_FOUND"


async def test_invitations_require_admin(cashier_client: AsyncClient) -> None:
    response = await cashier_client.get("/api/invitations")

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_invitations_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/invitations")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
