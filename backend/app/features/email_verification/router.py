# backend/app/features/email_verification/router.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dependencies import (
    PostCommitTasks,
    get_current_user,
    get_db,
    get_db_sessionmaker,
    get_email_client,
    get_post_commit_tasks,
    require_csrf,
)
from app.errors.openapi import error_responses
from app.features.users.model import User
from app.features.users.schemas import UserOut
from app.integrations.email import EmailClient

from . import service as email_verification_service
from .schemas import EmailVerificationVerify

# get_post_commit_tasks MUST come first: teardown is LIFO, so entering it before
# get_current_user (which opens the get_db session) is what makes the queued
# send_new_code job run after the request transaction commits.
router = APIRouter(
    prefix="/email-verification",
    tags=["email-verification"],
    dependencies=[
        Depends(get_post_commit_tasks),
        Depends(require_csrf),
        Depends(get_current_user),
    ],
    responses=error_responses(
        "UNAUTHENTICATED", "INVALID_SESSION", "INVALID_CSRF_TOKEN"
    ),
)


@router.post(
    "/verify",
    response_model=UserOut,
    responses=error_responses(
        "VERIFICATION_CODE_INVALID",
        "VERIFICATION_CODE_EXPIRED",
        "VERIFICATION_ALREADY_VERIFIED",
        "VALIDATION_FAILED",
    ),
)
async def verify(
    payload: EmailVerificationVerify,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserOut:
    """Confirm the emailed verification code for the current user.

    On success the account is marked verified and the updated user is returned.
    A wrong or expired code is rejected; request a new one via `/resend`.
    """
    user = await email_verification_service.verify_email(
        db, user=current_user, code=payload.code
    )
    return UserOut.model_validate(user)


@router.post(
    "/resend",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses("VERIFICATION_ALREADY_VERIFIED"),
)
async def resend(
    post_commit: Annotated[PostCommitTasks, Depends(get_post_commit_tasks)],
    sessionmaker: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_db_sessionmaker)
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    email_client: Annotated[EmailClient, Depends(get_email_client)],
) -> None:
    """Email the current user a fresh verification code.

    The previous code is invalidated. The email is sent after the request
    commits, via the same post-commit job registration uses.
    """
    await email_verification_service.resend(
        sessionmaker,
        post_commit=post_commit,
        email_client=email_client,
        user=current_user,
    )
