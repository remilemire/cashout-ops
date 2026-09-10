from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from authlib.integrations.starlette_client import OAuth

from app.core.config import settings

from .authlib import (
    GOOGLE_CLIENT_KWARGS,
    GOOGLE_SERVER_METADATA_URL,
    AuthlibOAuthClient,
)
from .client import OAuthClient
from .issuers import OAuthIssuer


@asynccontextmanager
async def oauth_lifespan() -> AsyncGenerator[OAuthClient]:
    """Build the configured OAuth client; no teardown is required."""
    yield _build_oauth_client()


def _build_oauth_client() -> OAuthClient:
    """Register each enabled issuer on a fresh Authlib registry.

    Issuer enablement is derived, not configured: an issuer whose credentials
    are set is registered (the same policy `enabled_issuers` exposes), and
    settings rejects a half-configured pair, so the truthiness check below is
    the whole condition — and narrows the optionals for the type checker.
    With no issuer configured the registry is empty and every flow fails at
    /start, before this client is ever asked for an authorization URL.
    """
    oauth = OAuth()
    if settings.auth.GOOGLE_CLIENT_ID and settings.auth.GOOGLE_CLIENT_SECRET:
        oauth.register(  # pyright: ignore[reportUnknownMemberType]
            OAuthIssuer.GOOGLE.value,
            client_id=settings.auth.GOOGLE_CLIENT_ID,
            client_secret=settings.auth.GOOGLE_CLIENT_SECRET,
            server_metadata_url=GOOGLE_SERVER_METADATA_URL,
            client_kwargs=GOOGLE_CLIENT_KWARGS,
        )
    return AuthlibOAuthClient(oauth)
