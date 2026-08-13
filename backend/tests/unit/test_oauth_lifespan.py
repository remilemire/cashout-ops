# backend/tests/unit/test_oauth_lifespan.py

"""Issuer enablement derives from credentials, in both the lifespan and
`enabled_issuers`."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.integrations.oauth import (
    AuthlibOAuthClient,
    OAuthExchangeError,
    OAuthIssuer,
    enabled_issuers,
)
from app.integrations.oauth.lifespan import oauth_lifespan


def _configure_google(
    monkeypatch: pytest.MonkeyPatch, *, client_id: str | None, client_secret: str | None
) -> None:
    monkeypatch.setattr(settings.auth, "GOOGLE_CLIENT_ID", client_id)
    monkeypatch.setattr(settings.auth, "GOOGLE_CLIENT_SECRET", client_secret)


async def test_configured_credentials_enable_google(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_google(
        monkeypatch,
        client_id="test-google-client-id",
        client_secret="test-google-client-secret",
    )

    assert enabled_issuers() == frozenset({OAuthIssuer.GOOGLE})
    async with oauth_lifespan() as client:
        assert isinstance(client, AuthlibOAuthClient)


async def test_absent_credentials_disable_google_but_boot_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # OAuth disabled must not break boot; the empty registry only rejects
    # flows if one is ever started.
    _configure_google(monkeypatch, client_id=None, client_secret=None)

    assert enabled_issuers() == frozenset()
    async with oauth_lifespan() as client:
        assert isinstance(client, AuthlibOAuthClient)
        with pytest.raises(OAuthExchangeError, match="not a registered"):
            await client.create_authorization_url(
                OAuthIssuer.GOOGLE, redirect_uri="http://localhost/callback"
            )


async def test_a_half_configured_pair_registers_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Settings rejects this state at load, so it can only exist on a mutated
    # settings object; the derivation still treats it as disabled rather than
    # registering an issuer with broken credentials.
    _configure_google(
        monkeypatch, client_id="test-google-client-id", client_secret=None
    )

    assert enabled_issuers() == frozenset()
    async with oauth_lifespan() as client:
        with pytest.raises(OAuthExchangeError, match="not a registered"):
            await client.create_authorization_url(
                OAuthIssuer.GOOGLE, redirect_uri="http://localhost/callback"
            )
