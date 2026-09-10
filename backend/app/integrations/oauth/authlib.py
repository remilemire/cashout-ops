from __future__ import annotations

from typing import cast

import httpx
from authlib.common.errors import AuthlibBaseError
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from joserfc.errors import JoseError

from app.core.schemas import normalize_email

from .errors import OAuthExchangeError
from .issuers import OAuthIssuer
from .types import OAuthAuthorization, OAuthIdentity, OAuthToken

GOOGLE_SERVER_METADATA_URL = (
    "https://accounts.google.com/.well-known/openid-configuration"
)
# openid puts a nonce-bound ID token in the token response; S256 makes Authlib
# mint a PKCE code_verifier with every authorization URL.
GOOGLE_CLIENT_KWARGS = {
    "scope": "openid email profile",
    "code_challenge_method": "S256",
}

# Everything an issuer interaction can raise: Authlib's own errors, the HTTP
# transport underneath, ID-token validation, and shape surprises in a response
# mapping. Wrapped so no provider-library type escapes this module.
_WRAPPED_ERRORS = (AuthlibBaseError, JoseError, httpx.HTTPError, KeyError, ValueError)


class AuthlibOAuthClient:
    """`OAuthClient` over Authlib's OAuth registry, request-free methods only.

    Deliberately never calls `authorize_redirect`/`authorize_access_token` —
    those persist flow state through Starlette's SessionMiddleware, which this
    app does not have. Custody of state/nonce/code_verifier belongs to the
    auth feature's Redis flow store; this client only mints and consumes them.
    """

    def __init__(self, oauth: OAuth) -> None:
        self._oauth = oauth

    def _app(self, issuer: OAuthIssuer) -> StarletteOAuth2App:
        # Authlib ships no type stubs, so each registry crossing in this
        # module pins the Unknown result with a cast or a targeted ignore.
        app = cast(
            "StarletteOAuth2App | None",
            self._oauth.create_client(issuer.value),  # pyright: ignore[reportUnknownMemberType]
        )
        if app is None:
            raise OAuthExchangeError(f"{issuer} is not a registered OAuth issuer.")
        return app

    async def create_authorization_url(
        self, issuer: OAuthIssuer, *, redirect_uri: str
    ) -> OAuthAuthorization:
        app = self._app(issuer)
        try:
            # prompt=select_account forces the issuer's account chooser every
            # time, instead of silently reusing a single active session.
            authorization = await app.create_authorization_url(  # pyright: ignore[reportUnknownMemberType]
                redirect_uri, prompt="select_account"
            )
            # nonce is present because the scope includes openid; code_verifier
            # because code_challenge_method is set. A registration that broke
            # either invariant surfaces here as the KeyError wrap.
            return OAuthAuthorization(
                url=authorization["url"],
                state=authorization["state"],
                nonce=authorization["nonce"],
                code_verifier=authorization["code_verifier"],
            )
        except _WRAPPED_ERRORS as error:
            raise OAuthExchangeError(
                f"Building the {issuer} authorization URL failed: {error!r}"
            ) from error

    async def exchange_token(
        self,
        issuer: OAuthIssuer,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> OAuthToken:
        # No `state=` here: state is compared by the flow service against its
        # Redis copy, not delegated to Authlib's session-bound handling.
        app = self._app(issuer)
        try:
            return cast(
                OAuthToken,
                await app.fetch_access_token(  # pyright: ignore[reportUnknownMemberType]
                    redirect_uri=redirect_uri, code=code, code_verifier=code_verifier
                ),
            )
        except _WRAPPED_ERRORS as error:
            raise OAuthExchangeError(
                f"The {issuer} code exchange failed: {error!r}"
            ) from error

    async def get_identity(
        self, issuer: OAuthIssuer, *, token: OAuthToken, nonce: str
    ) -> OAuthIdentity:
        app = self._app(issuer)
        try:
            # Validates signature, iss, aud, exp, and nonce against the
            # issuer's discovered metadata and JWKS (with a rotation retry).
            userinfo = await app.parse_id_token(dict(token), nonce=nonce)  # pyright: ignore[reportUnknownMemberType]
        except _WRAPPED_ERRORS as error:
            raise OAuthExchangeError(
                f"Validating the {issuer} ID token failed: {error!r}"
            ) from error

        subject = userinfo.get("sub")
        if not subject:
            raise OAuthExchangeError(f"The {issuer} ID token is missing 'sub'.")

        # The issuer's claim is normalized at this boundary rather than at its
        # use sites, so an issuer that echoes the address in the casing the
        # user typed still resolves to the one local account.
        email = userinfo.get("email")
        name = userinfo.get("name")
        return OAuthIdentity(
            issuer=issuer,
            subject=str(subject),
            email=normalize_email(str(email)) if email is not None else None,
            email_verified=bool(userinfo.get("email_verified", False)),
            name=str(name) if name is not None else None,
        )


__all__ = [
    "GOOGLE_CLIENT_KWARGS",
    "GOOGLE_SERVER_METADATA_URL",
    "AuthlibOAuthClient",
]
