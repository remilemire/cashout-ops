from __future__ import annotations

from pydantic import BaseModel

from app.integrations.oauth import OAuthIssuer


class StoredOAuthFlow(BaseModel):
    """Server-side state for a pending OAuth callback.

    Retains the expected state and nonce, the PKCE verifier, and the redirect
    target. The flow cookie holds only its id; state and nonce also appear
    in the authorization URL sent to the browser.
    """

    issuer: OAuthIssuer
    state: str
    nonce: str
    code_verifier: str
    redirect_to: str


__all__ = ["StoredOAuthFlow"]
