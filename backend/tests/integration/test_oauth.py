# backend/tests/integration/test_oauth.py

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.auth.external_identities.model import ExternalIdentity
from app.features.users.model import User
from app.infrastructure.redis import Redis
from app.integrations.oauth import OAuthExchangeError, OAuthIdentity, OAuthIssuer
from tests.support.factories import create_user
from tests.support.fakes import FakeOAuthClient
from tests.support.fakes.oauth import AuthorizationCall
from tests.support.fixtures.redis import redis_keys

CASHIER_EMAIL = "cashier@test.com"
GOOGLE_SUBJECT = "google-subject-1"

_START_URL = "/api/auth/oauth/google/start"
_CALLBACK_URL = "/api/auth/oauth/google/callback"


def _identity(
    *,
    subject: str = GOOGLE_SUBJECT,
    email: str | None = CASHIER_EMAIL,
    email_verified: bool = True,
) -> OAuthIdentity:
    return OAuthIdentity(
        issuer=OAuthIssuer.GOOGLE,
        subject=subject,
        email=email,
        email_verified=email_verified,
        name="Cashier",
    )


async def _start(
    client: AsyncClient,
    oauth_client: FakeOAuthClient,
    *,
    redirect_to: str = "/cashouts",
) -> AuthorizationCall:
    response = await client.get(_START_URL, params={"redirect_to": redirect_to})
    assert response.status_code == 302, response.text
    return oauth_client.latest_authorization()


async def _callback(
    client: AsyncClient, *, state: str, code: str = "auth-code"
) -> Response:
    return await client.get(_CALLBACK_URL, params={"code": code, "state": state})


async def _identities(db: AsyncSession) -> Sequence[ExternalIdentity]:
    return (await db.execute(select(ExternalIdentity))).scalars().all()


# ================================
# ------------ Start -------------
# ================================


async def test_start_redirects_to_the_issuer_with_a_flow_cookie(
    client: AsyncClient,
    redis_client: Redis,
    oauth_client: FakeOAuthClient,
) -> None:
    response = await client.get(_START_URL, params={"redirect_to": "/cashouts"})

    assert response.status_code == 302, response.text
    authorization = oauth_client.latest_authorization().authorization
    assert response.headers["location"] == authorization.url
    # The flow cookie is HttpOnly and carries only the flow id.
    assert "HttpOnly" in response.headers["set-cookie"]
    flow_id = client.cookies.get("oauth_flow")
    assert flow_id is not None

    # Starting never signs in: session cookies appear only after the callback.
    assert "session_token" not in client.cookies
    assert "csrf_token" not in client.cookies

    # Exactly one stored flow, keyed by the cookie's flow id, holding the
    # authorization secrets and the sanitized redirect target.
    [key] = await redis_keys(redis_client, "oauth_flow:*")
    assert key == f"oauth_flow:{flow_id}"
    raw = await redis_client.get(key)
    assert raw is not None
    stored = str(raw)
    assert authorization.state in stored
    assert authorization.nonce in stored
    assert authorization.code_verifier in stored
    assert "/cashouts" in stored

    # The issuer was asked to call back to the SPA-origin API path.
    base_url = settings.app.BASE_URL.rstrip("/")
    assert (
        oauth_client.latest_authorization().redirect_uri
        == f"{base_url}/api/auth/oauth/google/callback"
    )


async def test_start_for_a_disabled_issuer_redirects_with_the_error(
    client: AsyncClient,
    redis_client: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No enablement setting exists: removing the credential pair IS disabling.
    monkeypatch.setattr(settings.auth, "GOOGLE_CLIENT_ID", None)
    monkeypatch.setattr(settings.auth, "GOOGLE_CLIENT_SECRET", None)

    response = await client.get(_START_URL)

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/login?error=OAUTH_ISSUER_NOT_ENABLED"
    assert await redis_keys(redis_client, "oauth_flow:*") == []
    assert "oauth_flow" not in client.cookies


async def test_start_normalizes_a_malicious_redirect_target(
    client: AsyncClient,
    db_session: AsyncSession,
    oauth_client: FakeOAuthClient,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    oauth_client.identity = _identity()

    authorization = await _start(client, oauth_client, redirect_to="//evil.example")
    response = await _callback(client, state=authorization.authorization.state)

    # The crafted start link cannot bounce the signed-in user off-origin.
    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/"


# ================================
# ----------- Callback -----------
# ================================


async def test_first_sign_in_links_the_identity_and_signs_in(
    client: AsyncClient,
    db_session: AsyncSession,
    redis_client: Redis,
    oauth_client: FakeOAuthClient,
) -> None:
    user = await create_user(db_session, email=CASHIER_EMAIL)
    oauth_client.identity = _identity()

    authorization = await _start(client, oauth_client)
    response = await _callback(client, state=authorization.authorization.state)

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/cashouts"
    assert "session_token" in client.cookies
    assert "csrf_token" in client.cookies

    # The identity is linked to the matched account.
    [identity] = await _identities(db_session)
    assert identity.user_id == user.id
    assert identity.issuer is OAuthIssuer.GOOGLE
    assert identity.subject == GOOGLE_SUBJECT

    # The flow was consumed and its cookie cleared.
    assert await redis_keys(redis_client, "oauth_flow:*") == []
    assert "oauth_flow" not in client.cookies

    # PKCE/nonce custody round-trips: the exchange proved the verifier minted
    # at start, and validation used the stored nonce.
    assert oauth_client.exchanges[-1].code_verifier == (
        authorization.authorization.code_verifier
    )
    assert oauth_client.exchanges[-1].redirect_uri == authorization.redirect_uri
    assert oauth_client.identity_requests[-1].nonce == (
        authorization.authorization.nonce
    )


async def test_second_sign_in_matches_by_subject_even_when_email_changed(
    client: AsyncClient,
    db_session: AsyncSession,
    oauth_client: FakeOAuthClient,
) -> None:
    user = await create_user(db_session, email=CASHIER_EMAIL)
    oauth_client.identity = _identity()
    authorization = await _start(client, oauth_client)
    await _callback(client, state=authorization.authorization.state)

    # The issuer-side email changed; the subject claim still matches.
    oauth_client.identity = _identity(email="renamed@elsewhere.com")
    authorization = await _start(client, oauth_client)
    response = await _callback(client, state=authorization.authorization.state)

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/cashouts"
    [identity] = await _identities(db_session)
    assert identity.user_id == user.id


async def test_an_unverified_email_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    oauth_client: FakeOAuthClient,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    oauth_client.identity = _identity(email_verified=False)

    authorization = await _start(client, oauth_client)
    response = await _callback(client, state=authorization.authorization.state)

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/login?error=OAUTH_ACCOUNT_NOT_FOUND"
    assert await _identities(db_session) == []
    assert "session_token" not in client.cookies


async def test_an_unknown_account_is_rejected_never_created(
    client: AsyncClient,
    db_session: AsyncSession,
    oauth_client: FakeOAuthClient,
) -> None:
    oauth_client.identity = _identity(email="stranger@elsewhere.com")

    authorization = await _start(client, oauth_client)
    response = await _callback(client, state=authorization.authorization.state)

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/login?error=OAUTH_ACCOUNT_NOT_FOUND"
    assert await _identities(db_session) == []
    users = await db_session.execute(select(func.count()).select_from(User))
    assert users.scalar_one() == 0


async def test_a_state_mismatch_burns_the_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    oauth_client: FakeOAuthClient,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    oauth_client.identity = _identity()
    authorization = await _start(client, oauth_client)
    flow_id = client.cookies["oauth_flow"]

    tampered = await _callback(client, state="tampered-state")

    assert tampered.status_code == 302, tampered.text
    assert tampered.headers["location"] == "/login?error=OAUTH_FLOW_INVALID"
    assert oauth_client.exchanges == []

    # Consumption precedes verification, so even the correct state cannot be
    # replayed against a flow that has seen one bad callback.
    client.cookies.set("oauth_flow", flow_id)
    retried = await _callback(client, state=authorization.authorization.state)
    assert retried.headers["location"] == "/login?error=OAUTH_FLOW_INVALID"


async def test_a_completed_callback_cannot_be_replayed(
    client: AsyncClient,
    db_session: AsyncSession,
    oauth_client: FakeOAuthClient,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    oauth_client.identity = _identity()
    authorization = await _start(client, oauth_client)
    flow_id = client.cookies["oauth_flow"]

    completed = await _callback(client, state=authorization.authorization.state)
    assert completed.headers["location"] == "/cashouts"

    # An attacker replaying the exact same callback (with the flow cookie)
    # gets the unified error, not a second session.
    client.cookies.delete("session_token")
    client.cookies.delete("csrf_token")
    client.cookies.set("oauth_flow", flow_id)
    replayed = await _callback(client, state=authorization.authorization.state)

    assert replayed.status_code == 302, replayed.text
    assert replayed.headers["location"] == "/login?error=OAUTH_FLOW_INVALID"
    assert "session_token" not in client.cookies


async def test_an_expired_flow_is_rejected(
    client: AsyncClient,
    redis_client: Redis,
    oauth_client: FakeOAuthClient,
) -> None:
    authorization = await _start(client, oauth_client)
    # Redis TTLs enforce expiry, so an expired flow IS a missing key.
    [key] = await redis_keys(redis_client, "oauth_flow:*")
    await redis_client.delete(key)

    response = await _callback(client, state=authorization.authorization.state)

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/login?error=OAUTH_FLOW_INVALID"


async def test_a_callback_without_the_flow_cookie_is_rejected(
    client: AsyncClient,
    oauth_client: FakeOAuthClient,
) -> None:
    authorization = await _start(client, oauth_client)
    client.cookies.delete("oauth_flow")

    response = await _callback(client, state=authorization.authorization.state)

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/login?error=OAUTH_FLOW_INVALID"


async def test_a_denied_consent_callback_is_rejected(
    client: AsyncClient,
    oauth_client: FakeOAuthClient,
) -> None:
    authorization = await _start(client, oauth_client)

    # The issuer calls back with error=access_denied and no code.
    response = await client.get(
        _CALLBACK_URL,
        params={"error": "access_denied", "state": authorization.authorization.state},
    )

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/login?error=OAUTH_FLOW_INVALID"
    assert oauth_client.exchanges == []


async def test_issuer_failures_surface_as_the_unified_error(
    client: AsyncClient,
    db_session: AsyncSession,
    oauth_client: FakeOAuthClient,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    oauth_client.identity = _identity()

    oauth_client.fail_exchange_with = OAuthExchangeError("exchange boom")
    authorization = await _start(client, oauth_client)
    response = await _callback(client, state=authorization.authorization.state)
    assert response.headers["location"] == "/login?error=OAUTH_FLOW_INVALID"

    oauth_client.fail_exchange_with = None
    oauth_client.fail_identity_with = OAuthExchangeError("identity boom")
    authorization = await _start(client, oauth_client)
    response = await _callback(client, state=authorization.authorization.state)
    assert response.headers["location"] == "/login?error=OAUTH_FLOW_INVALID"
    assert "session_token" not in client.cookies


# ================================
# ---------- Concurrency ---------
# ================================


async def test_the_flow_is_single_use_under_concurrent_callbacks(
    client: AsyncClient,
    app: FastAPI,
    db_session: AsyncSession,
    oauth_client: FakeOAuthClient,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    oauth_client.identity = _identity()
    authorization = await _start(client, oauth_client)
    flow_id = client.cookies["oauth_flow"]
    state = authorization.authorization.state

    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as first,
        AsyncClient(transport=transport, base_url="http://test") as second,
    ):
        first.cookies.set("oauth_flow", flow_id)
        second.cookies.set("oauth_flow", flow_id)
        responses = await asyncio.gather(
            _callback(first, state=state), _callback(second, state=state)
        )

        locations = sorted(response.headers["location"] for response in responses)
        # The checked delete guarantees exactly one winner.
        assert locations == ["/cashouts", "/login?error=OAUTH_FLOW_INVALID"]
        winners = [
            http_client
            for http_client in (first, second)
            if "session_token" in http_client.cookies
        ]
        assert len(winners) == 1


# ================================
# ---------- Rate limits ---------
# ================================


async def test_start_is_rate_limited_per_ip(
    client: AsyncClient,
    oauth_client: FakeOAuthClient,
) -> None:
    for _ in range(settings.rate_limit.AUTH_IP_PER_HOUR):
        response = await client.get(_START_URL)
        assert response.status_code == 302, response.text

    limited = await client.get(_START_URL)

    assert limited.status_code == 429, limited.text
    assert limited.json()["code"] == "RATE_LIMITED"


async def test_callback_is_rate_limited_per_ip(
    client: AsyncClient,
) -> None:
    for _ in range(settings.rate_limit.AUTH_IP_PER_HOUR):
        response = await _callback(client, state="whatever")
        assert response.status_code == 302, response.text

    limited = await _callback(client, state="whatever")

    assert limited.status_code == 429, limited.text
    assert limited.json()["code"] == "RATE_LIMITED"


# ================================
# -------- Secret hygiene --------
# ================================


async def test_flow_secrets_never_reach_the_browser(
    client: AsyncClient,
    redis_client: Redis,
    oauth_client: FakeOAuthClient,
) -> None:
    response = await client.get(_START_URL, params={"redirect_to": "/cashouts"})

    assert response.status_code == 302, response.text
    authorization = oauth_client.latest_authorization().authorization
    set_cookie = response.headers["set-cookie"]
    # state necessarily rides the issuer URL; the verifier and nonce must
    # never leave the server in any channel the browser can read.
    assert authorization.code_verifier not in set_cookie
    assert authorization.nonce not in set_cookie
    assert authorization.code_verifier not in response.headers["location"]
    assert authorization.nonce not in response.headers["location"]
    assert response.content == b""

    # The cookie value is exactly the opaque flow id, not any secret.
    [key] = await redis_keys(redis_client, "oauth_flow:*")
    flow_id = key.removeprefix("oauth_flow:")
    assert client.cookies["oauth_flow"] == flow_id
    assert flow_id not in (
        authorization.state,
        authorization.nonce,
        authorization.code_verifier,
    )
