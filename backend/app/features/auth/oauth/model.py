# backend/app/features/auth/oauth/model.py

from __future__ import annotations

from pydantic import BaseModel

from app.integrations.oauth import OAuthIssuer


class StoredOAuthFlow(BaseModel):
    """A pending OAuth flow as persisted in Redis.

    Everything the callback must verify (`state`), prove (`code_verifier`),
    validate (`nonce`), and honor (`redirect_to`) is held server-side; the
    browser carries only the flow id, in the `oauth_flow` cookie.
    """

    issuer: OAuthIssuer
    state: str
    nonce: str
    code_verifier: str
    redirect_to: str


__all__ = ["StoredOAuthFlow"]
