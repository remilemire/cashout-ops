# backend/app/features/auth/router.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_csrf
from app.errors.openapi import error_responses
from app.features.sessions.cookies import (
    clear_csrf_cookie,
    clear_session_cookie,
    get_session_cookie,
    set_csrf_cookie,
    set_session_cookie,
)
from app.features.users.schemas import UserOut
from app.lib.crypto import generate_secret_token

from . import service as auth_service
from .schemas import AuthLogin, AuthRegister
from .types import UserWithSessionToken

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses("EMAIL_TAKEN", "VALIDATION_FAILED"),
)
async def register(
    response: Response,
    payload: AuthRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    """Create an account and start a session.

    Sets the `session_token` (HttpOnly) and `csrf_token` (JS-readable) cookies.
    The email matching `ADMIN_EMAIL` is promoted to the ADMIN role.
    """
    result = await auth_service.register(db, payload=payload)
    return _authenticated_response(response, result)


@router.post(
    "/login",
    response_model=UserOut,
    responses=error_responses("INVALID_CREDENTIALS", "VALIDATION_FAILED"),
)
async def login(
    response: Response,
    payload: AuthLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    """Authenticate with email and password.

    Sets the `session_token` (HttpOnly) and `csrf_token` (JS-readable) cookies.
    """
    result = await auth_service.login(db, payload=payload)
    return _authenticated_response(response, result)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf), Depends(get_current_user)],
    responses=error_responses(
        "UNAUTHENTICATED", "INVALID_SESSION", "INVALID_CSRF_TOKEN"
    ),
)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """End the current session and clear the auth cookies."""
    session_token = get_session_cookie(request)
    if session_token is not None:
        await auth_service.logout(db, session_token=session_token)

    clear_session_cookie(response)
    clear_csrf_cookie(response)


def _authenticated_response(
    response: Response, result: UserWithSessionToken
) -> UserOut:
    set_session_cookie(response, result.session_token)
    set_csrf_cookie(response, generate_secret_token())
    return UserOut.model_validate(result.user)
