from __future__ import annotations

from dataclasses import dataclass

from app.integrations.oauth import (
    OAuthAuthorization,
    OAuthClient,
    OAuthIdentity,
    OAuthIssuer,
    OAuthToken,
)


@dataclass(frozen=True)
class AuthorizationCall:
    issuer: OAuthIssuer
    redirect_uri: str
    authorization: OAuthAuthorization


@dataclass(frozen=True)
class ExchangeCall:
    issuer: OAuthIssuer
    code: str
    redirect_uri: str
    code_verifier: str


@dataclass(frozen=True)
class IdentityCall:
    issuer: OAuthIssuer
    token: OAuthToken
    nonce: str


class FakeOAuthClient(OAuthClient):
    """`OAuthClient` that mints predictable secrets and records every call.

    The fake authorization URL contains only state; unlike Authlib, it omits
    nonce and the PKCE challenge. Response tests using this fake do not prove
    the real authorization URL keeps nonce out of the browser.

    Configure `identity` with the OAuthIdentity a completed flow should
    resolve to (asserted present — a test that reaches get_identity without
    configuring one is broken). Set `fail_exchange_with`/`fail_identity_with`
    to make those steps raise instead, for testing issuer-failure paths.
    """

    def __init__(self) -> None:
        self.identity: OAuthIdentity | None = None
        self.authorizations: list[AuthorizationCall] = []
        self.exchanges: list[ExchangeCall] = []
        self.identity_requests: list[IdentityCall] = []
        self.fail_exchange_with: Exception | None = None
        self.fail_identity_with: Exception | None = None
        self._sequence = 0

    async def create_authorization_url(
        self, issuer: OAuthIssuer, *, redirect_uri: str
    ) -> OAuthAuthorization:
        self._sequence += 1
        n = self._sequence
        authorization = OAuthAuthorization(
            url=f"https://issuer.test/authorize?state=state-{n}",
            state=f"state-{n}",
            nonce=f"nonce-{n}",
            code_verifier=f"verifier-{n}",
        )
        self.authorizations.append(
            AuthorizationCall(
                issuer=issuer,
                redirect_uri=redirect_uri,
                authorization=authorization,
            )
        )
        return authorization

    async def exchange_token(
        self,
        issuer: OAuthIssuer,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> OAuthToken:
        if self.fail_exchange_with is not None:
            raise self.fail_exchange_with
        self.exchanges.append(
            ExchangeCall(
                issuer=issuer,
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        )
        return {"access_token": f"access-{code}", "id_token": f"id-{code}"}

    async def get_identity(
        self, issuer: OAuthIssuer, *, token: OAuthToken, nonce: str
    ) -> OAuthIdentity:
        if self.fail_identity_with is not None:
            raise self.fail_identity_with
        self.identity_requests.append(
            IdentityCall(issuer=issuer, token=token, nonce=nonce)
        )
        assert self.identity is not None, "FakeOAuthClient.identity not configured"
        return self.identity

    def latest_authorization(self) -> AuthorizationCall:
        assert self.authorizations, "no authorization URL was created"
        return self.authorizations[-1]


__all__ = ["AuthorizationCall", "ExchangeCall", "FakeOAuthClient", "IdentityCall"]
