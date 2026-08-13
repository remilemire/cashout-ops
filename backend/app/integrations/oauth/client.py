# backend/app/integrations/oauth/client.py

from __future__ import annotations

from typing import Protocol

from .issuers import OAuthIssuer
from .types import OAuthAuthorization, OAuthIdentity, OAuthToken


class OAuthClient(Protocol):
    """Provider-neutral primitives for OAuth sign-in (authorization code + PKCE).

    One client serves every enabled issuer, so each method takes the issuer
    it should act for. All three raise `OAuthExchangeError` on issuer
    failures; custody of the minted `state`/`nonce`/`code_verifier` between
    calls belongs to the caller.
    """

    async def create_authorization_url(
        self, issuer: OAuthIssuer, *, redirect_uri: str
    ) -> OAuthAuthorization:
        """Begin a flow: the issuer's authorization URL plus its secrets."""
        ...

    async def exchange_token(
        self,
        issuer: OAuthIssuer,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> OAuthToken:
        """Redeem the callback's authorization code for the issuer's token."""
        ...

    async def get_identity(
        self, issuer: OAuthIssuer, *, token: OAuthToken, nonce: str
    ) -> OAuthIdentity:
        """Validate the token's ID token and map it to a neutral identity."""
        ...


__all__ = ["OAuthClient"]
