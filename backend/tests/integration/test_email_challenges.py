# backend/tests/integration/test_email_challenges.py

from __future__ import annotations

import asyncio
import re

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.features.users.model import User
from app.features.users.types import UserRole
from app.infrastructure.outbox.messages.model import OutboxMessage
from app.infrastructure.redis import Redis
from tests.support.api import csrf_headers
from tests.support.factories import create_user
from tests.support.fakes import FakeEmailClient, LoginLink
from tests.support.fixtures.outbox import OutboxDrain
from tests.support.fixtures.redis import redis_keys

CASHIER_EMAIL = "cashier@test.com"


async def _initiate(client: AsyncClient, *, email: str = CASHIER_EMAIL) -> str:
    response = await client.post("/api/auth/email-challenges", json={"email": email})
    assert response.status_code == 202, response.text
    return response.json()["challengeId"]


async def _initiate_and_deliver(
    client: AsyncClient,
    drain_outbox: OutboxDrain,
    email_client: FakeEmailClient,
    *,
    email: str = CASHIER_EMAIL,
) -> LoginLink:
    """Start a challenge and deliver its link email, returning the link."""
    await _initiate(client, email=email)
    await drain_outbox()
    return email_client.latest_link(to=email)


async def _obtain_code(client: AsyncClient, link: LoginLink) -> str:
    response = await client.post(
        "/api/auth/email-challenges/verify-link",
        json={"challengeId": link.challenge_id, "token": link.token},
    )
    assert response.status_code == 200, response.text
    return response.json()["code"]


# ================================
# ---------- Initiation ----------
# ================================


async def test_start_login_returns_challenge_and_emails_link(
    client: AsyncClient,
    db_session: AsyncSession,
    redis_client: Redis,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)

    response = await client.post(
        "/api/auth/email-challenges", json={"email": CASHIER_EMAIL}
    )

    assert response.status_code == 202, response.text
    challenge_id = response.json()["challengeId"]
    # Initiation never signs in: no cookies until the code is verified.
    assert "session_token" not in client.cookies
    assert "csrf_token" not in client.cookies

    # The outbox message (delivered by the drain, as the dispatcher would in
    # production) emailed a single magic link for the challenge.
    assert await drain_outbox() == 1
    [email] = email_client.sent
    assert email.to == CASHIER_EMAIL
    assert f"/login/link?challenge={challenge_id}" in email.html
    assert "token=" in email.html

    # Exactly one stored challenge, holding the token's hash — never the token.
    [key] = await redis_keys(redis_client, "email_challenge:*")
    assert key == f"email_challenge:{challenge_id}"
    link = email_client.latest_link(to=CASHIER_EMAIL)
    raw = await redis_client.get(key)
    assert raw is not None
    assert link.token not in str(raw)


async def test_start_login_unknown_email_is_neutral(
    client: AsyncClient,
    redis_client: Redis,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    response = await client.post(
        "/api/auth/email-challenges", json={"email": "nobody@test.com"}
    )

    # A well-formed decoy id, indistinguishable from a real challenge —
    # nothing stored, nothing enqueued, no email.
    assert response.status_code == 202, response.text
    assert re.fullmatch(r"[0-9a-f-]{36}", response.json()["challengeId"])
    assert await drain_outbox() == 0
    assert await redis_keys(redis_client, "email_challenge:*") == []
    assert email_client.sent == []


async def test_start_login_for_owner_creates_no_account(
    client: AsyncClient,
    db_session: AsyncSession,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    # Everything short of the code is reachable by an unauthenticated stranger
    # — initiating, the link email going out, even clicking the link — so none
    # of it may create the privileged account.
    link = await _initiate_and_deliver(
        client, drain_outbox, email_client, email=settings.bootstrap.OWNER_EMAIL
    )
    await _obtain_code(client, link)

    users = (await db_session.execute(select(User))).scalars().all()
    assert len(users) == 0


async def test_start_login_for_owner_is_not_a_decoy(
    client: AsyncClient,
    redis_client: Redis,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    challenge_id = await _initiate(client, email=settings.bootstrap.OWNER_EMAIL)

    # Unlike an unknown address, the owner's gets a stored challenge and a
    # real email even though no account backs it yet.
    assert await drain_outbox() == 1
    [email] = email_client.sent
    assert email.to == settings.bootstrap.OWNER_EMAIL
    [key] = await redis_keys(redis_client, "email_challenge:*")
    assert key == f"email_challenge:{challenge_id}"


async def test_second_initiate_invalidates_previous_challenge(
    client: AsyncClient,
    db_session: AsyncSession,
    redis_client: Redis,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)

    link1 = await _initiate_and_deliver(client, drain_outbox, email_client)
    link2 = await _initiate_and_deliver(client, drain_outbox, email_client)

    # One active challenge per user: the second initiate destroyed the first.
    [key] = await redis_keys(redis_client, "email_challenge:*")
    assert key == f"email_challenge:{link2.challenge_id}"
    stale = await client.post(
        "/api/auth/email-challenges/verify-link",
        json={"challengeId": link1.challenge_id, "token": link1.token},
    )
    assert stale.status_code == 401
    assert stale.json()["code"] == "EMAIL_CHALLENGE_INVALID"

    # The newest link still completes the full sign-in.
    code = await _obtain_code(client, link2)
    ok = await client.post(
        "/api/auth/email-challenges/verify-code",
        json={"challengeId": link2.challenge_id, "code": code},
    )
    assert ok.status_code == 200, ok.text


# ================================
# ---------- Verify link ---------
# ================================


async def test_verify_link_returns_code_and_challenge_survives(
    client: AsyncClient,
    db_session: AsyncSession,
    redis_client: Redis,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    link = await _initiate_and_deliver(client, drain_outbox, email_client)

    response = await client.post(
        "/api/auth/email-challenges/verify-link",
        json={"challengeId": link.challenge_id, "token": link.token},
    )

    assert response.status_code == 200, response.text
    assert re.fullmatch(r"\d{6}", response.json()["code"])
    # The challenge survives for the verify-code step, but the link is spent.
    assert await redis_keys(redis_client, "email_challenge:*")
    replay = await client.post(
        "/api/auth/email-challenges/verify-link",
        json={"challengeId": link.challenge_id, "token": link.token},
    )
    assert replay.status_code == 401
    assert replay.json()["code"] == "EMAIL_CHALLENGE_INVALID"


async def test_verify_link_rejects_bad_token(
    client: AsyncClient,
    db_session: AsyncSession,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    link = await _initiate_and_deliver(client, drain_outbox, email_client)

    response = await client.post(
        "/api/auth/email-challenges/verify-link",
        json={"challengeId": link.challenge_id, "token": "not-the-token"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "EMAIL_CHALLENGE_INVALID"


async def test_verify_link_rejects_unknown_challenge(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/email-challenges/verify-link",
        json={
            "challengeId": "00000000-0000-0000-0000-000000000000",
            "token": "any-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "EMAIL_CHALLENGE_INVALID"


async def test_verify_link_before_delivery_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    # No drain: the challenge exists but no token has been minted yet.
    challenge_id = await _initiate(client)

    response = await client.post(
        "/api/auth/email-challenges/verify-link",
        json={"challengeId": challenge_id, "token": "any-token"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "EMAIL_CHALLENGE_INVALID"


async def test_verify_link_is_single_use(
    client: AsyncClient,
    db_session: AsyncSession,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    link = await _initiate_and_deliver(client, drain_outbox, email_client)
    code = await _obtain_code(client, link)

    # A second click of the same link is rejected outright.
    replay = await client.post(
        "/api/auth/email-challenges/verify-link",
        json={"challengeId": link.challenge_id, "token": link.token},
    )
    assert replay.status_code == 401
    assert replay.json()["code"] == "EMAIL_CHALLENGE_INVALID"

    # The code from the first (and only) verification still signs in.
    ok = await client.post(
        "/api/auth/email-challenges/verify-code",
        json={"challengeId": link.challenge_id, "code": code},
    )
    assert ok.status_code == 200, ok.text


# ================================
# ---------- Verify code ---------
# ================================


async def test_verify_code_signs_in_and_consumes(
    client: AsyncClient,
    db_session: AsyncSession,
    redis_client: Redis,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    link = await _initiate_and_deliver(client, drain_outbox, email_client)
    code = await _obtain_code(client, link)

    response = await client.post(
        "/api/auth/email-challenges/verify-code",
        json={"challengeId": link.challenge_id, "code": code},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == CASHIER_EMAIL
    # Inbound/outbound JSON is camelCase.
    assert body["fullName"] == "Test User"
    assert body["role"] == "staff"
    assert "session_token" in client.cookies
    assert "csrf_token" in client.cookies
    # A Redis-tracked session was minted; the challenge was consumed, and no
    # stale per-user pointer outlived it.
    assert await redis_keys(redis_client, "session:*")
    assert await redis_keys(redis_client, "email_challenge:*") == []
    assert await redis_keys(redis_client, "email_challenge_email:*") == []

    # Single use: replaying the same code fails.
    replay = await client.post(
        "/api/auth/email-challenges/verify-code",
        json={"challengeId": link.challenge_id, "code": code},
    )
    assert replay.status_code == 401
    assert replay.json()["code"] == "EMAIL_CHALLENGE_INVALID"


async def test_verify_code_bootstraps_owner(
    client: AsyncClient,
    db_session: AsyncSession,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    # No users exist: the owner account is created here, at the first sign-in
    # that proves control of the mailbox — not when the challenge started.
    link = await _initiate_and_deliver(
        client, drain_outbox, email_client, email=settings.bootstrap.OWNER_EMAIL
    )
    code = await _obtain_code(client, link)

    response = await client.post(
        "/api/auth/email-challenges/verify-code",
        json={"challengeId": link.challenge_id, "code": code},
    )

    assert response.status_code == 200, response.text
    me = await client.get("/api/users/me")
    assert me.json()["role"] == "owner"
    assert me.json()["fullName"] == "Owner"
    users = (await db_session.execute(select(User))).scalars().all()
    assert len(users) == 1


async def test_verify_code_does_not_duplicate_the_owner(
    client: AsyncClient,
    db_session: AsyncSession,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    owner_email = settings.bootstrap.OWNER_EMAIL
    for _ in range(2):
        link = await _initiate_and_deliver(
            client, drain_outbox, email_client, email=owner_email
        )
        code = await _obtain_code(client, link)
        response = await client.post(
            "/api/auth/email-challenges/verify-code",
            json={"challengeId": link.challenge_id, "code": code},
        )
        assert response.status_code == 200, response.text

    # The second sign-in found the account instead of bootstrapping it again.
    users = (await db_session.execute(select(User))).scalars().all()
    assert len(users) == 1
    assert users[0].role is UserRole.OWNER


async def test_verify_code_reports_a_blocked_owner_bootstrap_as_invalid(
    client: AsyncClient,
    owner_client: AsyncClient,
    db_session: AsyncSession,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    """A bootstrap that cannot take must not leak a 409 out of the login flow.

    Ownership moves to another admin and the bootstrap address is deleted, so
    the next sign-in for it tries to create a second owner. The SAVEPOINT in
    `add_if_unique` contains the unique-index violation, leaving the flow to
    answer with its own unified error — the same path a bootstrap losing a
    race to a concurrent sign-in takes.
    """
    owner_email = settings.bootstrap.OWNER_EMAIL
    heir = await create_user(db_session, email="heir@test.com", role=UserRole.ADMIN)
    transferred = await owner_client.post(
        f"/api/users/{heir.id}/transfer-ownership", headers=csrf_headers(owner_client)
    )
    assert transferred.status_code == 200, transferred.text
    former = (await owner_client.get("/api/users/me")).json()
    deleted = await owner_client.delete(
        f"/api/users/{former['id']}", headers=csrf_headers(owner_client)
    )
    assert deleted.status_code == 204, deleted.text

    link = await _initiate_and_deliver(
        client, drain_outbox, email_client, email=owner_email
    )
    code = await _obtain_code(client, link)
    response = await client.post(
        "/api/auth/email-challenges/verify-code",
        json={"challengeId": link.challenge_id, "code": code},
    )

    assert response.status_code == 401, response.text
    assert response.json()["code"] == "EMAIL_CHALLENGE_INVALID"
    # The heir is still the one and only owner.
    owners = (
        (await db_session.execute(select(User).where(User.role == UserRole.OWNER)))
        .scalars()
        .all()
    )
    assert [owner.id for owner in owners] == [heir.id]


async def test_verify_code_wrong_code_is_capped(
    client: AsyncClient,
    db_session: AsyncSession,
    redis_client: Redis,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    link = await _initiate_and_deliver(client, drain_outbox, email_client)
    code = await _obtain_code(client, link)
    wrong_code = "000000" if code != "000000" else "000001"

    # Four wrong guesses each fail but leave the challenge alive.
    for _ in range(4):
        response = await client.post(
            "/api/auth/email-challenges/verify-code",
            json={"challengeId": link.challenge_id, "code": wrong_code},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "EMAIL_CHALLENGE_INVALID"
        assert await redis_keys(redis_client, "email_challenge:*")

    # The fifth exhausts the cap and destroys the challenge outright.
    fifth = await client.post(
        "/api/auth/email-challenges/verify-code",
        json={"challengeId": link.challenge_id, "code": wrong_code},
    )
    assert fifth.status_code == 401
    assert await redis_keys(redis_client, "email_challenge:*") == []
    assert await redis_keys(redis_client, "email_challenge_email:*") == []

    # Even the correct code is dead now.
    final = await client.post(
        "/api/auth/email-challenges/verify-code",
        json={"challengeId": link.challenge_id, "code": code},
    )
    assert final.status_code == 401


async def test_verify_code_attempt_cap_holds_under_concurrency(
    client: AsyncClient,
    db_session: AsyncSession,
    redis_client: Redis,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    link = await _initiate_and_deliver(client, drain_outbox, email_client)
    code = await _obtain_code(client, link)
    wrong_code = "000000" if code != "000000" else "000001"

    # Ten wrong guesses race in parallel. The attempt counter is a
    # server-atomic INCR, so at most MAX_CODE_ATTEMPTS of them ever reach the
    # code comparison — a racy counter would let every request read attempts=0
    # and leave the challenge alive.
    responses = await asyncio.gather(
        *(
            client.post(
                "/api/auth/email-challenges/verify-code",
                json={"challengeId": link.challenge_id, "code": wrong_code},
            )
            for _ in range(10)
        )
    )

    for response in responses:
        assert response.status_code == 401
        assert response.json()["code"] == "EMAIL_CHALLENGE_INVALID"
    # The cap was exhausted, so the challenge was destroyed outright.
    assert await redis_keys(redis_client, "email_challenge:*") == []
    assert await redis_keys(redis_client, "email_challenge_email:*") == []

    # Even the correct code is dead now.
    final = await client.post(
        "/api/auth/email-challenges/verify-code",
        json={"challengeId": link.challenge_id, "code": code},
    )
    assert final.status_code == 401
    assert final.json()["code"] == "EMAIL_CHALLENGE_INVALID"


async def test_verify_code_after_user_deleted_is_rejected(
    client: AsyncClient,
    admin_client: AsyncClient,
    db_session: AsyncSession,
    redis_client: Redis,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    user = await create_user(db_session, email=CASHIER_EMAIL)
    link = await _initiate_and_deliver(client, drain_outbox, email_client)
    code = await _obtain_code(client, link)
    # The account vanishes between link delivery and code submission.
    deleted = await admin_client.delete(
        f"/api/users/{user.id}", headers=csrf_headers(admin_client)
    )
    assert deleted.status_code == 204, deleted.text
    sessions_before = await redis_keys(redis_client, "session:*")

    response = await client.post(
        "/api/auth/email-challenges/verify-code",
        json={"challengeId": link.challenge_id, "code": code},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "EMAIL_CHALLENGE_INVALID"
    # No session was minted for the deleted account (only the admin's own
    # pre-existing session remains).
    assert await redis_keys(redis_client, "session:*") == sessions_before


async def test_verify_code_expired_challenge_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    redis_client: Redis,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    link = await _initiate_and_deliver(client, drain_outbox, email_client)
    code = await _obtain_code(client, link)
    # Expiry is enforced by the Redis TTL, so an expired challenge IS a missing
    # key; deleting the key is exactly what expiry looks like to the service.
    [key] = await redis_keys(redis_client, "email_challenge:*")
    await redis_client.delete(key)

    response = await client.post(
        "/api/auth/email-challenges/verify-code",
        json={"challengeId": link.challenge_id, "code": code},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "EMAIL_CHALLENGE_INVALID"


# ================================
# ----------- Delivery -----------
# ================================


async def test_send_failure_is_recorded_for_retry(
    client: AsyncClient,
    db_session: AsyncSession,
    db_sessionmaker: async_sessionmaker[AsyncSession],
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    email_client.fail_with = RuntimeError("provider down")

    await _initiate(client)
    assert await drain_outbox() == 1

    # The failed attempt sent nothing and left the message pending retry, with
    # a concise application-level error — no stack trace, no provider guts.
    assert email_client.sent == []
    async with db_sessionmaker() as db:
        stmt = select(OutboxMessage).where(
            OutboxMessage.type == "auth.send_login_link_email",
            OutboxMessage.completed_at.is_(None),
        )
        message = (await db.execute(stmt)).scalar_one()
    assert message.dead_lettered_at is None
    assert message.attempts == 1
    assert message.max_attempts == 5
    assert message.last_error == "RuntimeError: provider down"
