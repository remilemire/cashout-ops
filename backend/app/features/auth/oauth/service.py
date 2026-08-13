# backend/app/features/auth/oauth/service.py

"""OAuth sign-in orchestration (the flow state machine).

/start mints the issuer authorization URL and stores the flow's secrets
(state, nonce, PKCE verifier) in Redis under a fresh flow id; the browser
carries only that id, in the `oauth_flow` cookie. The issuer's callback
consumes the flow, verifies state, redeems the code, validates the identity,
and resolves it to a local account via the external-identities service.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import AppError
from app.infrastructure.redis import Redis
from app.integrations.oauth import (
    OAuthClient,
    OAuthExchangeError,
    OAuthIssuer,
    enabled_issuers,
)

from . import store
from .external_identities import service as external_identities_service
from .model import StoredOAuthFlow

if TYPE_CHECKING:
    from app.features.users.model import User


@dataclass(frozen=True)
class StartedOAuthFlow:
    flow_id: str
    authorization_url: str


@dataclass(frozen=True)
class CompletedOAuthFlow:
    user: User
    redirect_to: str


def _callback_uri(issuer: OAuthIssuer) -> str:
    # Built from the SPA's public base URL: the /api path rides the Vite
    # proxy in dev and is same-origin in prod. This exact value is what the
    # issuer whitelists, and the token exchange must repeat it verbatim.
    base_url = settings.app.BASE_URL.rstrip("/")
    return f"{base_url}/api/auth/oauth/{issuer.value}/callback"


def sanitize_redirect_to(redirect_to: str | None) -> str:
    """Keep only a same-origin relative path; anything else becomes "/".

    Rejects protocol-relative ("//host") and backslash ("/\\") forms, so a
    crafted start link can never bounce a signed-in user off-origin. Falling
    back instead of failing preserves the sign-in over a malformed
    convenience parameter.
    """
    if (
        redirect_to
        and redirect_to.startswith("/")
        and not redirect_to.startswith("//")
        and not redirect_to.startswith("/\\")
    ):
        return redirect_to
    return "/"


async def start(
    redis: Redis,
    oauth_client: OAuthClient,
    *,
    issuer: OAuthIssuer,
    redirect_to: str | None,
) -> StartedOAuthFlow:
    """Begin a flow: store its secrets and return the issuer URL to visit."""
    if issuer not in enabled_issuers():
        raise AppError("OAUTH_ISSUER_NOT_ENABLED")

    try:
        authorization = await oauth_client.create_authorization_url(
            issuer, redirect_uri=_callback_uri(issuer)
        )
    except OAuthExchangeError as error:
        raise AppError("OAUTH_SIGN_IN_FAILED", str(error)) from error

    flow_id = str(uuid4())
    await store.save(
        redis,
        flow_id=flow_id,
        flow=StoredOAuthFlow(
            issuer=issuer,
            state=authorization.state,
            nonce=authorization.nonce,
            code_verifier=authorization.code_verifier,
            redirect_to=sanitize_redirect_to(redirect_to),
        ),
    )

    return StartedOAuthFlow(flow_id=flow_id, authorization_url=authorization.url)


async def complete(
    db: AsyncSession,
    redis: Redis,
    oauth_client: OAuthClient,
    *,
    issuer: OAuthIssuer,
    flow_id: str,
    code: str | None,
    state: str | None,
) -> CompletedOAuthFlow:
    """Consume the flow and resolve the issuer identity to a local user.

    Every failure mode raises the one unified error so the response shape
    cannot reveal which check failed. The router completes sign-in via
    `access.grant`.
    """
    flow = await store.find(redis, flow_id=flow_id)
    if flow is None or flow.issuer is not issuer:
        raise AppError("OAUTH_SIGN_IN_FAILED")

    # Consume BEFORE verifying: the checked delete makes the flow single-use
    # under concurrent callbacks, and a failed verification can never be
    # retried against the same state and verifier.
    if not await store.delete(redis, flow_id=flow_id):
        raise AppError("OAUTH_SIGN_IN_FAILED")

    # A denied consent screen calls back with no code; treat it as the same
    # unified failure rather than distinguishing it.
    if code is None or state is None or not secrets.compare_digest(flow.state, state):
        raise AppError("OAUTH_SIGN_IN_FAILED")

    try:
        token = await oauth_client.exchange_token(
            issuer,
            code=code,
            redirect_uri=_callback_uri(issuer),
            code_verifier=flow.code_verifier,
        )
        identity = await oauth_client.get_identity(
            issuer, token=token, nonce=flow.nonce
        )
    except OAuthExchangeError as error:
        raise AppError("OAUTH_SIGN_IN_FAILED", str(error)) from error

    user = await external_identities_service.resolve_user(db, identity=identity)

    return CompletedOAuthFlow(user=user, redirect_to=flow.redirect_to)


__all__ = [
    "CompletedOAuthFlow",
    "StartedOAuthFlow",
    "complete",
    "sanitize_redirect_to",
    "start",
]
