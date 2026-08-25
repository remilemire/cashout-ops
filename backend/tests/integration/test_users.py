# backend/tests/integration/test_users.py

from __future__ import annotations

from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.features.users import service as users_service
from app.features.users.model import User
from app.features.users.schemas import UserCreate
from app.features.users.types import UserRole
from tests.support.api import OWNER_EMAIL, csrf_headers, login
from tests.support.cashout import create_submission
from tests.support.factories import create_user
from tests.support.fakes import FakeEmailClient
from tests.support.fixtures.clients import ClientFactory
from tests.support.fixtures.outbox import OutboxDrain


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
    assert "admin@test.com" in [user["email"] for user in body]


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
    assert body["role"] == "staff"
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


# ================================
# ---------- Update user ---------
# ================================


async def test_admin_updates_user_name(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, email="staff@test.com", full_name="Old Name")

    response = await admin_client.patch(
        f"/api/users/{user.id}",
        json={"fullName": "New Name"},
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["fullName"] == "New Name"
    # Persisted, not just echoed back.
    listed = (await admin_client.get("/api/users")).json()
    names = {entry["email"]: entry["fullName"] for entry in listed}
    assert names["staff@test.com"] == "New Name"


async def test_admin_updates_own_name(admin_client: AsyncClient) -> None:
    me = (await admin_client.get("/api/users/me")).json()

    response = await admin_client.patch(
        f"/api/users/{me['id']}",
        json={"fullName": "Renamed Admin"},
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 200, response.text
    assert (await admin_client.get("/api/users/me")).json()["fullName"] == (
        "Renamed Admin"
    )


async def test_admin_updates_owner_name(
    admin_client: AsyncClient, owner_client: AsyncClient
) -> None:
    owner = (await owner_client.get("/api/users/me")).json()

    response = await admin_client.patch(
        f"/api/users/{owner['id']}",
        json={"fullName": "Renamed Owner"},
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 200, response.text
    # A rename is not a role change: the owner keeps their role.
    body = response.json()
    assert body["fullName"] == "Renamed Owner"
    assert body["role"] == "owner"


async def test_update_user_requires_admin(
    cashier_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, email="staff@test.com")

    response = await cashier_client.patch(
        f"/api/users/{user.id}",
        json={"fullName": "New Name"},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_update_unknown_user_not_found(admin_client: AsyncClient) -> None:
    response = await admin_client.patch(
        f"/api/users/{uuid4()}",
        json={"fullName": "New Name"},
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "USER_NOT_FOUND"


async def test_update_user_rejects_blank_name(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, email="staff@test.com", full_name="Old Name")

    response = await admin_client.patch(
        f"/api/users/{user.id}",
        json={"fullName": ""},
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert [issue["path"] for issue in body["issues"]] == [["fullName"]]


async def test_update_user_rejects_role_and_email_fields(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, email="staff@test.com")

    response = await admin_client.patch(
        f"/api/users/{user.id}",
        json={"fullName": "New Name", "role": "admin", "email": "hijack@test.com"},
        headers=csrf_headers(admin_client),
    )

    # BaseIn forbids extras: the endpoint renames and nothing else.
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


# ================================
# ---------- Roles ---------------
# ================================


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
    assert body["role"] == "admin"


async def test_admin_demotes_user(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, email="other@test.com", role=UserRole.ADMIN)

    response = await admin_client.post(
        f"/api/users/{user.id}/demote", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["role"] == "staff"


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
    user = await create_user(db_session, email="staff@test.com", role=UserRole.ADMIN)

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
    assert me["role"] == "admin"  # self-demotion is the realistic lockout risk

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


async def test_promote_owner_is_forbidden(
    admin_client: AsyncClient, owner_client: AsyncClient
) -> None:
    owner = (await owner_client.get("/api/users/me")).json()
    assert owner["role"] == "owner"

    response = await admin_client.post(
        f"/api/users/{owner['id']}/promote", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CANNOT_MODIFY_OWNER"


async def test_demote_owner_is_forbidden(
    admin_client: AsyncClient, owner_client: AsyncClient
) -> None:
    owner = (await owner_client.get("/api/users/me")).json()

    response = await admin_client.post(
        f"/api/users/{owner['id']}/demote", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CANNOT_MODIFY_OWNER"


# ================================
# ---------- Delete user ---------
# ================================


async def test_deleted_user_loses_access(
    admin_client: AsyncClient,
    client: AsyncClient,
    db_session: AsyncSession,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Seeded directly, then logged in through the API for a real session.
    # Deletion does not revoke sessions; the deleted-user lookup during
    # authentication is the backstop that turns the lingering session away.
    user = await create_user(db_session, email="doomed@test.com")
    await login(
        client,
        email="doomed@test.com",
        drain_outbox=drain_outbox,
        email_client=email_client,
    )
    assert (await client.get("/api/users/me")).status_code == 200

    response = await admin_client.delete(
        f"/api/users/{user.id}", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 204, response.text
    # The deleted user's session no longer authenticates (the user row is
    # gone, even though the Redis key may linger); the admin's own survives.
    assert (await client.get("/api/users/me")).status_code == 401
    assert (await admin_client.get("/api/users/me")).status_code == 200


async def test_delete_user_without_submissions_hard_deletes(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, email="fresh@test.com")

    response = await admin_client.delete(
        f"/api/users/{user.id}", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 204, response.text
    listed = (await admin_client.get("/api/users")).json()
    assert "fresh@test.com" not in [entry["email"] for entry in listed]
    # No submissions reference them, so the row is gone outright — not just
    # stamped deleted.
    stmt = select(User).where(User.email == "fresh@test.com")
    assert (await db_session.execute(stmt)).scalar_one_or_none() is None


async def test_delete_user_with_submissions_soft_deletes(
    admin_client: AsyncClient,
    make_client: ClientFactory,
    db_session: AsyncSession,
) -> None:
    author_client = await make_client(email="author@test.com", full_name="Busy Author")
    submission_id = await create_submission(author_client)
    author = (await author_client.get("/api/users/me")).json()

    response = await admin_client.delete(
        f"/api/users/{author['id']}", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 204, response.text
    # Gone from the accounts list...
    listed = (await admin_client.get("/api/users")).json()
    assert "author@test.com" not in [entry["email"] for entry in listed]
    # ...and their lingering session is dead.
    turned_away = await author_client.get("/api/users/me")
    assert turned_away.status_code == 401
    assert turned_away.json()["code"] == "INVALID_SESSION"
    # But history keeps its author: the admin still sees the submission
    # under their name.
    submissions = (await admin_client.get("/api/cashout/submissions")).json()
    entry = next(item for item in submissions if item["id"] == submission_id)
    assert entry["submittedBy"]["fullName"] == "Busy Author"
    # The row survives, stamped as deleted.
    stmt = select(User).where(User.email == "author@test.com")
    row = (await db_session.execute(stmt)).scalar_one()
    assert row.deleted_at is not None


async def test_soft_deleted_user_can_be_reinvited(
    admin_client: AsyncClient,
    make_client: ClientFactory,
    client: AsyncClient,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    # An admin author, to prove reinviting never restores old privileges.
    author_client = await make_client(
        email="rehire@test.com", full_name="Old Name", role=UserRole.ADMIN
    )
    await create_submission(author_client)
    author = (await author_client.get("/api/users/me")).json()
    deleted = await admin_client.delete(
        f"/api/users/{author['id']}", headers=csrf_headers(admin_client)
    )
    assert deleted.status_code == 204, deleted.text

    response = await admin_client.post(
        "/api/users",
        json={"email": "rehire@test.com", "fullName": "New Name"},
        headers=csrf_headers(admin_client),
    )

    # No EMAIL_TAKEN: the soft-deleted row is revived — the same row (so
    # their old submissions' FKs stay intact), renamed, and reset to staff.
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] == author["id"]
    assert body["fullName"] == "New Name"
    assert body["role"] == "staff"

    # The revived account can sign in through the email-challenge flow.
    await login(
        client,
        email="rehire@test.com",
        drain_outbox=drain_outbox,
        email_client=email_client,
    )
    assert (await client.get("/api/users/me")).status_code == 200


async def test_soft_deleted_user_cannot_sign_in(
    admin_client: AsyncClient,
    make_client: ClientFactory,
    client: AsyncClient,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    author_client = await make_client(email="gone@test.com")
    await create_submission(author_client)
    author = (await author_client.get("/api/users/me")).json()
    deleted = await admin_client.delete(
        f"/api/users/{author['id']}", headers=csrf_headers(admin_client)
    )
    assert deleted.status_code == 204, deleted.text
    email_client.sent.clear()

    response = await client.post(
        "/api/auth/email-challenges", json={"email": "gone@test.com"}
    )

    # The address gets the unknown-address decoy treatment: a well-formed
    # challenge id, but nothing enqueued and no email sent.
    assert response.status_code == 202, response.text
    assert await drain_outbox() == 0
    assert email_client.sent == []


async def test_delete_owner_is_forbidden(
    admin_client: AsyncClient, owner_client: AsyncClient
) -> None:
    owner = (await owner_client.get("/api/users/me")).json()

    response = await admin_client.delete(
        f"/api/users/{owner['id']}", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CANNOT_DELETE_OWNER"
    # The owner is untouched.
    assert (await owner_client.get("/api/users/me")).status_code == 200


async def test_delete_requires_admin(
    cashier_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, email="staff@test.com")

    response = await cashier_client.delete(
        f"/api/users/{user.id}", headers=csrf_headers(cashier_client)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_delete_unknown_user_not_found(admin_client: AsyncClient) -> None:
    response = await admin_client.delete(
        f"/api/users/{uuid4()}", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "USER_NOT_FOUND"


# ================================
# ------ Transfer ownership ------
# ================================


async def test_owner_transfers_ownership_to_admin(
    owner_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_user(db_session, email="heir@test.com", role=UserRole.ADMIN)

    response = await owner_client.post(
        f"/api/users/{admin.id}/transfer-ownership",
        headers=csrf_headers(owner_client),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(admin.id)
    assert body["role"] == "owner"
    # The previous owner is now a plain admin (still authorized to list).
    users = (await owner_client.get("/api/users")).json()
    roles = {user["email"]: user["role"] for user in users}
    assert roles[OWNER_EMAIL] == "admin"
    assert roles["heir@test.com"] == "owner"


async def test_transfer_ownership_requires_owner(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    other = await create_user(db_session, email="other@test.com", role=UserRole.ADMIN)

    response = await admin_client.post(
        f"/api/users/{other.id}/transfer-ownership",
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_transfer_ownership_to_staff_conflicts(
    owner_client: AsyncClient, db_session: AsyncSession
) -> None:
    staff = await create_user(db_session, email="staff@test.com")

    response = await owner_client.post(
        f"/api/users/{staff.id}/transfer-ownership",
        headers=csrf_headers(owner_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "TRANSFER_TARGET_NOT_ADMIN"
    # The owner keeps their role.
    assert (await owner_client.get("/api/users/me")).json()["role"] == "owner"


async def test_transfer_ownership_to_unknown_user_not_found(
    owner_client: AsyncClient,
) -> None:
    response = await owner_client.post(
        f"/api/users/{uuid4()}/transfer-ownership",
        headers=csrf_headers(owner_client),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "USER_NOT_FOUND"


# ================================
# ------ Bootstrap the owner -----
# ================================


async def test_bootstrap_owner_loses_a_race_without_poisoning_its_session(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Two transactions bootstrapping the owner at once: exactly one takes.

    The loser reports the loss by returning None rather than raising, and its
    session survives the contained unique-index violation — without the
    SAVEPOINT in `add_if_unique` the failed flush would poison the whole
    request transaction, so the caller could not go on to answer with the
    sign-in flow's own error.
    """
    payload = UserCreate(
        email=settings.bootstrap.OWNER_EMAIL,
        full_name=settings.bootstrap.OWNER_FULL_NAME,
    )

    async with db_sessionmaker() as first, db_sessionmaker() as second:
        winner = await users_service.bootstrap_owner(first, payload=payload)
        assert winner is not None
        assert winner.role is UserRole.OWNER
        await first.commit()

        loser = await users_service.bootstrap_owner(second, payload=payload)

        assert loser is None
        # The session is still usable, and still sees a single owner.
        existing = await users_service.find_by_email(second, email=payload.email)
        assert existing is not None
        assert existing.role is UserRole.OWNER
        await second.commit()
