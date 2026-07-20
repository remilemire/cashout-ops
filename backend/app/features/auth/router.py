# backend/app/features/auth/router.py

from __future__ import annotations

from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dependencies import (
    PostCommitTasks,
    get_db,
    get_db_sessionmaker,
    get_email_client,
    get_post_commit_tasks,
)
from app.errors.openapi import error_responses
from app.features.email_verification import service as email_verification_service
from app.features.sessions.cookies import (
    clear_csrf_cookie,
    clear_session_cookie,
    get_session_cookie,
    set_csrf_cookie,
    set_session_cookie,
)
from app.features.users.schemas import UserOut
from app.integrations.email import EmailClient
from app.lib.crypto import generate_secret_token

from . import service as auth_service
from .schemas import AuthLogin, AuthRegister
from .types import UserWithSessionToken

router = APIRouter(prefix="/auth", tags=["auth"])


# get_post_commit_tasks is listed first so it tears down after get_db commits:
# the verification code is issued + emailed only once the new user is persisted.
@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_post_commit_tasks)],
    responses=error_responses(
        "EMAIL_TAKEN", "INVITATION_REQUIRED", "VALIDATION_FAILED"
    ),
)
async def register(
    response: Response,
    payload: AuthRegister,
    post_commit: Annotated[PostCommitTasks, Depends(get_post_commit_tasks)],
    db: Annotated[AsyncSession, Depends(get_db)],
    sessionmaker: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_db_sessionmaker)
    ],
    email_client: Annotated[EmailClient, Depends(get_email_client)],
) -> UserOut:
    """Create an account and start a session.

    Sets the `session_token` (HttpOnly) and `csrf_token` (JS-readable) cookies.
    Registration requires a pending invitation for the email; the invitation is
    marked accepted. The email matching `ADMIN_EMAIL` is exempt and is created
    with the ADMIN role. A verification code is emailed after the request
    commits (via a post-commit job); the account stays unverified until it's
    confirmed.
    """
    result = await auth_service.register(db, payload=payload)

    if result.user.email_verified_at is None:
        post_commit.add(
            partial(
                email_verification_service.send_new_code,
                sessionmaker,
                email_client=email_client,
                user_id=result.user.id,
            )
        )

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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """End the current session and clear the auth cookies.

    Best-effort and unauthenticated: a missing or already-invalid session still
    clears the cookies and returns 204 rather than erroring.
    """
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
