# backend/tests/integration/test_rate_limits.py

"""Rate limiting on the pre-session auth endpoints and the cashout quotas.

The passwordless routes carry two layers: per-identifier limits (email
address, challenge id) against targeted abuse, and per-IP caps on request
volume from one source. The AI-costly cashout endpoints carry per-user
quotas bounding provider spend. All requests here share the test client's
IP; the autouse FLUSHDB between tests resets every counter.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.auth.email_challenges.dependencies import MAX_LINK_ATTEMPTS
from app.infrastructure.redis import Redis
from tests.support.api import csrf_headers
from tests.support.cashout import (
    configure_server_summary,
    create_submission,
    upload_document,
)
from tests.support.documents import SAMPLE_PDF_BYTES, SAMPLE_PNG_UPLOAD
from tests.support.factories import create_user
from tests.support.fakes import FakeAIClient, FakeEmailClient, LoginLink
from tests.support.fixtures.clients import ClientFactory
from tests.support.fixtures.outbox import OutboxDrain
from tests.support.fixtures.redis import redis_keys

CASHIER_EMAIL = "cashier@test.com"

# The catalog body every 429 carries, regardless of which limit fired.
RATE_LIMITED_KIND = "TOO_MANY_REQUESTS"
RATE_LIMITED_CODE = "RATE_LIMITED"
RATE_LIMITED_MESSAGE = "Too many attempts. Please wait a moment and try again."


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


# ================================
# ----- Initiate — per email -----
# ================================


async def test_initiate_per_email_is_limited_with_retry_after(
    client: AsyncClient,
    db_session: AsyncSession,
    redis_client: Redis,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)

    for _ in range(settings.rate_limit.INITIATE_EMAIL_PER_HOUR):
        await _initiate(client)

    response = await client.post(
        "/api/auth/email-challenges", json={"email": CASHIER_EMAIL}
    )

    assert response.status_code == 429, response.text
    body = response.json()
    assert body["kind"] == RATE_LIMITED_KIND
    assert body["code"] == RATE_LIMITED_CODE
    retry_after = response.headers["Retry-After"]
    assert retry_after.isdigit()
    assert 0 < int(retry_after) <= 3600

    # The counter key exists, holds only the address's hash — never the raw
    # email (no PII in Redis keys) — and expires with the window.
    [key] = await redis_keys(redis_client, "rate_limit:auth_initiate_email:*")
    assert all(CASHIER_EMAIL not in k for k in await redis_keys(redis_client, "*"))
    ttl = int(await redis_client.ttl(key))
    assert 0 < ttl <= 3600

    # The limit is keyed per email: a different address still initiates.
    await _initiate(client, email="someone-else@test.com")


async def test_initiate_limit_is_enumeration_safe(client: AsyncClient) -> None:
    # No user row exists for this address: the limiter fires before any user
    # lookup, so the 429 is byte-identical to the real-account case.
    for _ in range(settings.rate_limit.INITIATE_EMAIL_PER_HOUR):
        await _initiate(client, email="nobody@test.com")

    response = await client.post(
        "/api/auth/email-challenges", json={"email": "nobody@test.com"}
    )

    assert response.status_code == 429, response.text
    assert response.json() == {
        "kind": RATE_LIMITED_KIND,
        "code": RATE_LIMITED_CODE,
        "message": RATE_LIMITED_MESSAGE,
    }


async def test_rate_limit_window_expiry_restores_access(
    client: AsyncClient, redis_client: Redis
) -> None:
    for _ in range(settings.rate_limit.INITIATE_EMAIL_PER_HOUR):
        await _initiate(client, email="nobody@test.com")
    blocked = await client.post(
        "/api/auth/email-challenges", json={"email": "nobody@test.com"}
    )
    assert blocked.status_code == 429, blocked.text

    # The window is enforced by the Redis TTL, so an elapsed window IS a
    # missing key; deleting the key is exactly what expiry looks like to the
    # limiter.
    [key] = await redis_keys(redis_client, "rate_limit:auth_initiate_email:*")
    await redis_client.delete(key)

    await _initiate(client, email="nobody@test.com")


# ================================
# ------ Initiate — per IP -------
# ================================


async def test_initiate_per_ip_is_limited(client: AsyncClient) -> None:
    # Every request uses a unique address, staying far under the per-email
    # limit — only the shared client IP accumulates.
    for i in range(settings.rate_limit.AUTH_IP_PER_HOUR):
        await _initiate(client, email=f"unique-{i}@test.com")

    response = await client.post(
        "/api/auth/email-challenges", json={"email": "unique-final@test.com"}
    )

    assert response.status_code == 429, response.text
    assert response.json()["code"] == RATE_LIMITED_CODE


# ================================
# ---------- Verify link ---------
# ================================


async def test_verify_link_per_challenge_is_limited(
    client: AsyncClient,
    db_session: AsyncSession,
    email_client: FakeEmailClient,
    drain_outbox: OutboxDrain,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    link = await _initiate_and_deliver(client, drain_outbox, email_client)

    for _ in range(MAX_LINK_ATTEMPTS):
        response = await client.post(
            "/api/auth/email-challenges/verify-link",
            json={"challengeId": link.challenge_id, "token": "not-the-token"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "EMAIL_CHALLENGE_INVALID"

    # The challenge-keyed limit fires before the service runs: even the
    # correct token gets 429 once the budget is spent.
    final = await client.post(
        "/api/auth/email-challenges/verify-link",
        json={"challengeId": link.challenge_id, "token": link.token},
    )
    assert final.status_code == 429, final.text
    assert final.json()["code"] == RATE_LIMITED_CODE


# ================================
# ---------- Verify code ---------
# ================================


async def test_verify_code_per_ip_is_limited(client: AsyncClient) -> None:
    # The per-challenge budget on this endpoint is the service's atomic
    # MAX_CODE_ATTEMPTS counter; the route-level guard is per IP only.
    for i in range(settings.rate_limit.AUTH_IP_PER_HOUR):
        response = await client.post(
            "/api/auth/email-challenges/verify-code",
            json={"challengeId": f"missing-{i}", "code": "000000"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "EMAIL_CHALLENGE_INVALID"

    final = await client.post(
        "/api/auth/email-challenges/verify-code",
        json={"challengeId": "missing-final", "code": "000000"},
    )
    assert final.status_code == 429, final.text
    assert final.json()["code"] == RATE_LIMITED_CODE


# ================================
# -- Cashout — per-user quotas ---
# ================================


async def test_upload_documents_per_user_is_limited(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    make_client: ClientFactory,
    drain_outbox: OutboxDrain,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.rate_limit, "UPLOADS_PER_USER_PER_HOUR", 2)
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)

    # Two uploads with distinct bytes (duplicate checksums are rejected)
    # spend the whole quota.
    await upload_document(cashier_client, submission_id, drain=drain_outbox)
    await upload_document(
        cashier_client, submission_id, drain=drain_outbox, file=SAMPLE_PNG_UPLOAD
    )

    response = await cashier_client.post(
        f"/api/cashout/submissions/{submission_id}/documents",
        files={"file": ("third.pdf", SAMPLE_PDF_BYTES + b" third", "application/pdf")},
        headers=csrf_headers(cashier_client),
    )

    assert response.status_code == 429, response.text
    body = response.json()
    assert body["kind"] == RATE_LIMITED_KIND
    assert body["code"] == RATE_LIMITED_CODE
    assert response.headers["Retry-After"].isdigit()

    # The quota is keyed per user: another cashier still uploads freely.
    other = await make_client(email="other-cashier@test.com")
    other_submission_id = await create_submission(other)
    await upload_document(other, other_submission_id, drain=drain_outbox)


async def test_extract_per_user_is_limited(
    cashier_client: AsyncClient,
    ai_client: FakeAIClient,
    drain_outbox: OutboxDrain,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.rate_limit, "EXTRACTS_PER_USER_PER_HOUR", 1)
    configure_server_summary(ai_client)
    submission_id = await create_submission(cashier_client)
    created = await upload_document(cashier_client, submission_id, drain=drain_outbox)
    url = f"/api/cashout/documents/{created['cashoutDocumentId']}/extract"

    first = await cashier_client.post(url, headers=csrf_headers(cashier_client))
    assert first.status_code == 200, first.text

    # Run the re-queued extraction so the analysis leaves EXTRACTING: absent
    # the limiter the second call would succeed, so the 429 below can only
    # come from the quota (the guard dependency fires before the handler).
    await drain_outbox()

    second = await cashier_client.post(url, headers=csrf_headers(cashier_client))
    assert second.status_code == 429, second.text
    body = second.json()
    assert body["kind"] == RATE_LIMITED_KIND
    assert body["code"] == RATE_LIMITED_CODE
    assert second.headers["Retry-After"].isdigit()
