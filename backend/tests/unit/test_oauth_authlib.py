# backend/tests/unit/test_oauth_authlib.py

"""The Authlib client builds authorization URLs that force the account chooser."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from authlib.integrations.starlette_client import OAuth

from app.integrations.oauth.authlib import GOOGLE_CLIENT_KWARGS, AuthlibOAuthClient
from app.integrations.oauth.issuers import OAuthIssuer


def _google_client() -> AuthlibOAuthClient:
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
    return AuthlibOAuthClient(oauth)


async def test_authorization_url_forces_the_account_chooser() -> None:
    authorization = await _google_client().create_authorization_url(
        OAuthIssuer.GOOGLE, redirect_uri="http://localhost/callback"
    )

    params = parse_qs(urlparse(authorization.url).query)
    assert params["prompt"] == ["select_account"]
