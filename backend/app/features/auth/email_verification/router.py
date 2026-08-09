# backend/app/features/auth/email_verification/router.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, get_redis, require_csrf
from app.errors.openapi import error_responses
from app.features.users.model import User
from app.features.users.schemas import UserOut
from app.infrastructure.redis import Redis

from . import service as email_verification_service
from .schemas import EmailVerificationVerify

router = APIRouter(
    prefix="/email-verification",
    tags=["auth"],
    dependencies=[
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
    redis: Annotated[Redis, Depends(get_redis)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserOut:
    """Confirm the emailed verification code for the current user.

    On success the account is marked verified and the updated user is returned.
    A wrong or expired code is rejected; request a new one via `/resend`.
    """
    user = await email_verification_service.verify_email(
        db, redis, user=current_user, code=payload.code
    )
    return UserOut.model_validate(user)


@router.post(
    "/resend",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses("VERIFICATION_ALREADY_VERIFIED"),
)
async def resend(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Email the current user a fresh verification code.

    The previous code is invalidated. The email is sent after the request
    commits, via the same outbox message registration enqueues.
    """
    await email_verification_service.resend(db, user=current_user)
