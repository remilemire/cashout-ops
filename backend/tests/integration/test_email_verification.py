# backend/tests/integration/test_email_verification.py

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.auth.outbox import send_verification_email_message
from app.infrastructure.outbox.messages.model import OutboxMessage
from app.infrastructure.redis import Redis
from tests.support.api import csrf_headers
from tests.support.fakes import FakeEmailClient
from tests.support.fixtures.outbox import OutboxDrain
from tests.support.fixtures.redis import redis_keys

CASHIER_EMAIL = "cashier@test.com"


# ================================
# ---------- Registration --------
# ================================


async def test_register_emails_code_and_leaves_account_unverified(
    unverified_client: AsyncClient,
    email_client: FakeEmailClient,
    redis_client: Redis,
) -> None:
    me = await unverified_client.get("/api/users/me")
    assert me.json()["emailVerifiedAt"] is None

    # The outbox message (drained by the client fixture, as the dispatcher
    # would in production) emailed a single code and stored its hash in Redis.
    assert [email.to for email in email_client.sent] == [CASHIER_EMAIL]
    assert await redis_keys(redis_client, "email_verification:*")


# ================================
# ------------- Gate -------------
# ================================


async def test_unverified_user_is_blocked_from_guarded_routes(
    unverified_client: AsyncClient,
) -> None:
    # /users/me stays reachable, but a verification-guarded route is blocked.
    assert (await unverified_client.get("/api/users/me")).status_code == 200

    response = await unverified_client.get("/api/cashout/submissions")
    assert response.status_code == 403
    assert response.json()["code"] == "EMAIL_NOT_VERIFIED"


async def test_verifying_unlocks_guarded_routes(
    unverified_client: AsyncClient, email_client: FakeEmailClient
) -> None:
    code = email_client.latest_code(to=CASHIER_EMAIL)
    await unverified_client.post(
        "/api/auth/email-verification/verify",
        json={"code": code},
        headers=csrf_headers(unverified_client),
    )

    response = await unverified_client.get("/api/cashout/submissions")
    assert response.status_code == 200


# ================================
# ------------ Verify ------------
# ================================


async def test_verify_marks_user_verified_and_consumes_the_code(
    unverified_client: AsyncClient,
    email_client: FakeEmailClient,
    redis_client: Redis,
) -> None:
    code = email_client.latest_code(to=CASHIER_EMAIL)

    response = await unverified_client.post(
        "/api/auth/email-verification/verify",
        json={"code": code},
        headers=csrf_headers(unverified_client),
    )

    assert response.status_code == 200, response.text
    assert response.json()["emailVerifiedAt"] is not None
    me = await unverified_client.get("/api/users/me")
    assert me.json()["emailVerifiedAt"] is not None
    # The code is consumed on success: its Redis key is deleted.
    assert await redis_keys(redis_client, "email_verification:*") == []


async def test_verify_wrong_code_is_invalid(unverified_client: AsyncClient) -> None:
    response = await unverified_client.post(
        "/api/auth/email-verification/verify",
        json={"code": "000000"},
        headers=csrf_headers(unverified_client),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VERIFICATION_CODE_INVALID"


async def test_verify_expired_code(
    unverified_client: AsyncClient,
    email_client: FakeEmailClient,
    redis_client: Redis,
) -> None:
    code = email_client.latest_code(to=CASHIER_EMAIL)
    # Expiry is enforced by the Redis TTL, so an expired code IS a missing key;
    # deleting the key is exactly what expiry looks like to the service.
    [key] = await redis_keys(redis_client, "email_verification:*")
    await redis_client.delete(key)

    response = await unverified_client.post(
        "/api/auth/email-verification/verify",
        json={"code": code},
        headers=csrf_headers(unverified_client),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VERIFICATION_CODE_EXPIRED"


async def test_verify_already_verified_conflicts(
    unverified_client: AsyncClient, email_client: FakeEmailClient
) -> None:
    code = email_client.latest_code(to=CASHIER_EMAIL)
    headers = csrf_headers(unverified_client)
    first = await unverified_client.post(
        "/api/auth/email-verification/verify", json={"code": code}, headers=headers
    )
    assert first.status_code == 200

    response = await unverified_client.post(
        "/api/auth/email-verification/verify", json={"code": code}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["code"] == "VERIFICATION_ALREADY_VERIFIED"


async def test_verify_requires_authentication(client: AsyncClient) -> None:
    # Pass the double-submit CSRF check (matching cookie + header) so the
    # request reaches the auth gate rather than stopping at require_csrf.
    client.cookies.set("csrf_token", "test-token")

    response = await client.post(
        "/api/auth/email-verification/verify",
        json={"code": "123456"},
        headers={"x-csrf-token": "test-token"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


# ================================
# ------------ Resend ------------
# ================================


async def test_resend_issues_a_new_code_and_supersedes_the_old(
    unverified_client: AsyncClient,
    email_client: FakeEmailClient,
    redis_client: Redis,
    drain_outbox: OutboxDrain,
) -> None:
    old_code = email_client.latest_code(to=CASHIER_EMAIL)
    headers = csrf_headers(unverified_client)

    resent = await unverified_client.post(
        "/api/auth/email-verification/resend", headers=headers
    )
    assert resent.status_code == 204
    # The resend only enqueued the message; delivery happens at dispatch.
    assert await drain_outbox() == 1

    new_code = email_client.latest_code(to=CASHIER_EMAIL)
    assert new_code != old_code
    # The SET overwrote the previous code: still exactly one key per user.
    assert len(await redis_keys(redis_client, "email_verification:*")) == 1

    # The superseded code no longer verifies; the fresh one does.
    stale = await unverified_client.post(
        "/api/auth/email-verification/verify", json={"code": old_code}, headers=headers
    )
    assert stale.status_code == 400
    assert stale.json()["code"] == "VERIFICATION_CODE_INVALID"
    ok = await unverified_client.post(
        "/api/auth/email-verification/verify", json={"code": new_code}, headers=headers
    )
    assert ok.status_code == 200


async def test_resend_send_failure_is_recorded_for_retry(
    unverified_client: AsyncClient,
    email_client: FakeEmailClient,
    db_sessionmaker: async_sessionmaker[AsyncSession],
    drain_outbox: OutboxDrain,
) -> None:
    email_client.fail_with = RuntimeError("provider down")
    sent_before = len(email_client.sent)

    resent = await unverified_client.post(
        "/api/auth/email-verification/resend",
        headers=csrf_headers(unverified_client),
    )
    assert resent.status_code == 204
    assert await drain_outbox() == 1

    # The failed attempt sent nothing and left the message pending retry, with
    # a concise application-level error — no stack trace, no provider guts.
    assert len(email_client.sent) == sent_before
    async with db_sessionmaker() as db:
        stmt = select(OutboxMessage).where(
            OutboxMessage.type == send_verification_email_message.type,
            OutboxMessage.completed_at.is_(None),
        )
        message = (await db.execute(stmt)).scalar_one()
    assert message.dead_lettered_at is None
    assert message.attempts == 1
    assert message.max_attempts == 5
    assert message.last_error == "RuntimeError: provider down"


async def test_resend_after_verification_conflicts(
    unverified_client: AsyncClient, email_client: FakeEmailClient
) -> None:
    code = email_client.latest_code(to=CASHIER_EMAIL)
    headers = csrf_headers(unverified_client)
    await unverified_client.post(
        "/api/auth/email-verification/verify", json={"code": code}, headers=headers
    )

    response = await unverified_client.post(
        "/api/auth/email-verification/resend", headers=headers
    )
    assert response.status_code == 409
    assert response.json()["code"] == "VERIFICATION_ALREADY_VERIFIED"
