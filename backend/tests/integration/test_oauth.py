from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.auth.models import ExternalIdentity
from app.features.users.model import User
from app.features.users.types import UserRole
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
    # The unified error: the redirect cannot say the email was unverified.
    assert response.headers["location"] == "/login?error=OAUTH_SIGN_IN_FAILED"
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
    # Byte-identical to every other post-authorization failure, so the
    # redirect never reveals that this deployment has no such account.
    assert response.headers["location"] == "/login?error=OAUTH_SIGN_IN_FAILED"
    assert await _identities(db_session) == []
    users = await db_session.execute(select(func.count()).select_from(User))
    assert users.scalar_one() == 0


async def test_first_sign_in_at_the_bootstrap_address_creates_the_owner(
    client: AsyncClient,
    db_session: AsyncSession,
    oauth_client: FakeOAuthClient,
) -> None:
    """The owner bootstrap is not the email challenge's alone.

    No account exists yet, so the deployment's first sign-in is necessarily
    an unmatched identity. The issuer's verified-email claim is the mailbox
    proof the bootstrap needs, so BOOTSTRAP_OWNER_EMAIL claims ownership
    here exactly as it would through the emailed code.
    """
    oauth_client.identity = _identity(email=settings.bootstrap.OWNER_EMAIL)

    authorization = await _start(client, oauth_client)
    response = await _callback(client, state=authorization.authorization.state)

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/cashouts"
    me = await client.get("/api/users/me")
    assert me.json()["role"] == "owner"
    # The name comes from BOOTSTRAP_OWNER_FULL_NAME, not the issuer profile,
    # so the owner is the same account whichever flow bootstraps it.
    assert me.json()["fullName"] == "Owner"

    # The account exists once, with the identity linked to it, so the next
    # sign-in matches by subject rather than bootstrapping again.
    users = (await db_session.execute(select(User))).scalars().all()
    assert [(user.email, user.role) for user in users] == [
        (settings.bootstrap.OWNER_EMAIL, UserRole.OWNER)
    ]
    [identity] = await _identities(db_session)
    assert identity.user_id == users[0].id
    assert identity.subject == GOOGLE_SUBJECT


async def test_the_bootstrap_address_cannot_claim_an_existing_ownership(
    client: AsyncClient,
    db_session: AsyncSession,
    oauth_client: FakeOAuthClient,
) -> None:
    # Ownership already lives elsewhere, so the bootstrap address is just an
    # unknown one — the same gate the email challenge applies.
    await create_user(db_session, email="heir@test.com", role=UserRole.OWNER)
    oauth_client.identity = _identity(email=settings.bootstrap.OWNER_EMAIL)

    authorization = await _start(client, oauth_client)
    response = await _callback(client, state=authorization.authorization.state)

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/login?error=OAUTH_SIGN_IN_FAILED"
    assert "session_token" not in client.cookies
    assert await _identities(db_session) == []
    users = (await db_session.execute(select(User))).scalars().all()
    assert [user.email for user in users] == ["heir@test.com"]


async def test_an_unverified_bootstrap_address_never_bootstraps(
    client: AsyncClient,
    db_session: AsyncSession,
    oauth_client: FakeOAuthClient,
) -> None:
    # The verified-email claim IS the proof the bootstrap rests on: without
    # it, holding the address at the issuer proves nothing about the mailbox.
    oauth_client.identity = _identity(
        email=settings.bootstrap.OWNER_EMAIL, email_verified=False
    )

    authorization = await _start(client, oauth_client)
    response = await _callback(client, state=authorization.authorization.state)

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/login?error=OAUTH_SIGN_IN_FAILED"
    assert "session_token" not in client.cookies
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
    assert tampered.headers["location"] == "/login?error=OAUTH_SIGN_IN_FAILED"
    assert oauth_client.exchanges == []

    # Consumption precedes verification, so even the correct state cannot be
    # replayed against a flow that has seen one bad callback.
    client.cookies.set("oauth_flow", flow_id)
    retried = await _callback(client, state=authorization.authorization.state)
    assert retried.headers["location"] == "/login?error=OAUTH_SIGN_IN_FAILED"


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
    assert replayed.headers["location"] == "/login?error=OAUTH_SIGN_IN_FAILED"
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
    assert response.headers["location"] == "/login?error=OAUTH_SIGN_IN_FAILED"


async def test_a_callback_without_the_flow_cookie_is_rejected(
    client: AsyncClient,
    oauth_client: FakeOAuthClient,
) -> None:
    authorization = await _start(client, oauth_client)
    client.cookies.delete("oauth_flow")

    response = await _callback(client, state=authorization.authorization.state)

    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/login?error=OAUTH_SIGN_IN_FAILED"


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
    assert response.headers["location"] == "/login?error=OAUTH_SIGN_IN_FAILED"
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
    assert response.headers["location"] == "/login?error=OAUTH_SIGN_IN_FAILED"

    oauth_client.fail_exchange_with = None
    oauth_client.fail_identity_with = OAuthExchangeError("identity boom")
    authorization = await _start(client, oauth_client)
    response = await _callback(client, state=authorization.authorization.state)
    assert response.headers["location"] == "/login?error=OAUTH_SIGN_IN_FAILED"
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
        assert locations == ["/cashouts", "/login?error=OAUTH_SIGN_IN_FAILED"]
        winners = [
            http_client
            for http_client in (first, second)
            if "session_token" in http_client.cookies
        ]
        assert len(winners) == 1


async def test_a_link_race_reports_the_same_unified_error(
    client: AsyncClient,
    app: FastAPI,
    db_session: AsyncSession,
    oauth_client: FakeOAuthClient,
) -> None:
    await create_user(db_session, email=CASHIER_EMAIL)
    oauth_client.identity = _identity()

    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as first,
        AsyncClient(transport=transport, base_url="http://test") as second,
    ):
        # Separate flows, so both callbacks clear the single-use check and
        # both reach the insert of the same (issuer, subject) link.
        first_flow = await _start(first, oauth_client)
        second_flow = await _start(second, oauth_client)
        responses = await asyncio.gather(
            _callback(first, state=first_flow.authorization.state),
            _callback(second, state=second_flow.authorization.state),
        )

        locations = sorted(response.headers["location"] for response in responses)
        # The loser's unique violation is reported as the unified error, not
        # as a conflict code that would mark this identity as known here.
        assert locations == ["/cashouts", "/login?error=OAUTH_SIGN_IN_FAILED"]
        winners = [
            http_client
            for http_client in (first, second)
            if "session_token" in http_client.cookies
        ]
        assert len(winners) == 1

    # The unique index held: exactly one link exists for the identity.
    [identity] = await _identities(db_session)
    assert identity.subject == GOOGLE_SUBJECT


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


async def test_fake_flow_response_keeps_values_out_of_cookie(
    client: AsyncClient,
    redis_client: Redis,
    oauth_client: FakeOAuthClient,
) -> None:
    response = await client.get(_START_URL, params={"redirect_to": "/cashouts"})

    assert response.status_code == 302, response.text
    authorization = oauth_client.latest_authorization().authorization
    set_cookie = response.headers["set-cookie"]
    # The cookie carries only a flow ID. This fake URL omits nonce as well;
    # Authlib's real authorization URL includes nonce and state. These checks
    # cover the route's response to the fake, not Authlib's URL construction.
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
