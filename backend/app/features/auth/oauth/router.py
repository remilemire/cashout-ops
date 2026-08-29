# backend/app/features/auth/oauth/router.py

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse

from app.errors import AppError, error_responses
from app.features.auth.shared import access
from app.infrastructure.db.dependencies import DbSession
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis
from app.integrations.oauth import OAuthClient, OAuthIssuer
from app.integrations.oauth.dependencies import get_oauth_client

from . import service as oauth_service
from .cookies import (
    clear_oauth_flow_cookie,
    get_oauth_flow_cookie,
    set_oauth_flow_cookie,
)
from .dependencies import rate_limit_oauth_callback_ip, rate_limit_oauth_start_ip

# No auth or CSRF dependencies: both routes are pre-session, top-level GET
# navigations (the same posture as the email-challenge routes). Because a
# browser navigation cannot consume the JSON error contract, this router
# converts service failures into redirects the login page renders — the only
# JSON errors left are the dependency-raised 429 and the enum path-param 422.
router = APIRouter(prefix="/oauth", tags=["auth"])


def _redirect_responses(description: str) -> dict[int | str, dict[str, Any]]:
    return {
        **error_responses("RATE_LIMITED", "VALIDATION_FAILED"),
        status.HTTP_302_FOUND: {"description": description},
    }


def _error_redirect(code: str) -> RedirectResponse:
    # The catalog code is the whole payload — no message text leaks into URLs.
    response = RedirectResponse(
        f"/login?error={code}", status_code=status.HTTP_302_FOUND
    )
    clear_oauth_flow_cookie(response)
    return response


@router.get(
    "/{issuer}/start",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    responses=_redirect_responses(
        "To the issuer's authorization page, with the `oauth_flow` cookie "
        "set; to `/login?error={code}` on failure."
    ),
    dependencies=[Depends(rate_limit_oauth_start_ip)],
)
async def start_oauth(
    issuer: OAuthIssuer,
    redis: Annotated[Redis, Depends(get_redis)],
    oauth_client: Annotated[OAuthClient, Depends(get_oauth_client)],
    redirect_to: str | None = None,
) -> RedirectResponse:
    """Begin an OAuth sign-in as a top-level navigation.

    `redirect_to` (a relative SPA path) is stored server-side with the flow
    and honored after the callback; it is never read back from the issuer.
    """
    try:
        flow = await oauth_service.start(
            redis, oauth_client, issuer=issuer, redirect_to=redirect_to
        )
    except AppError as error:
        return _error_redirect(error.code)

    response = RedirectResponse(
        flow.authorization_url, status_code=status.HTTP_302_FOUND
    )
    set_oauth_flow_cookie(response, flow.flow_id)
    return response


@router.get(
    "/{issuer}/callback",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    responses=_redirect_responses(
        "Into the SPA (the flow's `redirect_to`) with the session cookies "
        "set; to `/login?error={code}` on failure."
    ),
    dependencies=[Depends(rate_limit_oauth_callback_ip)],
)
async def oauth_callback(
    issuer: OAuthIssuer,
    request: Request,
    db: DbSession,
    redis: Annotated[Redis, Depends(get_redis)],
    oauth_client: Annotated[OAuthClient, Depends(get_oauth_client)],
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    """Complete the sign-in the issuer redirected back to.

    Consumes the flow (single use), verifies state against the Redis copy,
    exchanges the code, validates the identity, and starts a cookie session.
    """
    flow_id = get_oauth_flow_cookie(request)
    if flow_id is None:
        return _error_redirect("OAUTH_SIGN_IN_FAILED")

    try:
        completed = await oauth_service.complete(
            db,
            redis,
            oauth_client,
            issuer=issuer,
            flow_id=flow_id,
            code=code,
            state=state,
        )
    except AppError:
        # The code is discarded rather than forwarded: every failure the
        # issuer's callback can reach reports the one code, so the redirect
        # cannot tell a rejected identity apart from a broken flow.
        return _error_redirect("OAUTH_SIGN_IN_FAILED")

    response = RedirectResponse(
        completed.redirect_to, status_code=status.HTTP_302_FOUND
    )
    clear_oauth_flow_cookie(response)
    await access.grant(redis, response, user_id=completed.user.id)
    return response
