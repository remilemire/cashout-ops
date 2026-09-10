"""What the Authlib client puts on the wire, and what it reads back off it.

The authorization URL must force the account chooser; the identity it parses
out of an ID token must carry a normalized address.
"""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import pytest
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App

from app.integrations.oauth.authlib import GOOGLE_CLIENT_KWARGS, AuthlibOAuthClient
from app.integrations.oauth.issuers import OAuthIssuer


def _google_registry() -> OAuth:
    # Explicit endpoints instead of GOOGLE_SERVER_METADATA_URL so the URL builds
    # offline: no discovery fetch, just the query params this client adds.
    oauth = OAuth()
    oauth.register(  # pyright: ignore[reportUnknownMemberType]
        OAuthIssuer.GOOGLE.value,
        client_id="test-google-client-id",
        client_secret="test-google-client-secret",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        access_token_url="https://oauth2.googleapis.com/token",
        client_kwargs=GOOGLE_CLIENT_KWARGS,
    )
    return oauth


def _google_client() -> AuthlibOAuthClient:
    return AuthlibOAuthClient(_google_registry())


async def test_authorization_url_forces_the_account_chooser() -> None:
    authorization = await _google_client().create_authorization_url(
        OAuthIssuer.GOOGLE, redirect_uri="http://localhost/callback"
    )

    params = parse_qs(urlparse(authorization.url).query)
    assert params["prompt"] == ["select_account"]


async def test_the_issuer_email_claim_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mixed-case claim resolves to the same local account as any other casing.

    Folded here rather than where identities are consumed, so nothing
    downstream has to remember that an issuer's casing is not authoritative —
    the address it hands back is already the form the users table holds.
    """
    oauth = _google_registry()
    # Authlib ships no type stubs, so pin the registry crossing with a cast,
    # as app/integrations/oauth/authlib.py does.
    app = cast(
        "StarletteOAuth2App | None",
        oauth.create_client(OAuthIssuer.GOOGLE.value),  # pyright: ignore[reportUnknownMemberType]
    )
    assert app is not None

    async def _parse_id_token(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "sub": "google-subject",
            "email": "Chef@Bistro.COM",
            "email_verified": True,
            "name": "Chef",
        }

    monkeypatch.setattr(app, "parse_id_token", _parse_id_token)

    identity = await AuthlibOAuthClient(oauth).get_identity(
        OAuthIssuer.GOOGLE, token={"id_token": "stub"}, nonce="stub-nonce"
    )

    assert identity.email == "chef@bistro.com"
    assert identity.email_verified is True
