# backend/app/features/users/router.py

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_current_user,
    get_db,
    require_admin,
    require_csrf,
    require_verified_user,
)
from app.errors.openapi import error_responses

from . import service as users_service
from .model import User
from .schemas import UserOut

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_csrf), Depends(get_current_user)],
    responses=error_responses("UNAUTHENTICATED", "INVALID_SESSION"),
)


@router.get("/me", response_model=UserOut)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserOut:
    """Return the authenticated user."""
    return UserOut.model_validate(current_user)


@router.get(
    "",
    response_model=list[UserOut],
    dependencies=[Depends(require_verified_user), Depends(require_admin)],
    responses=error_responses("FORBIDDEN", "EMAIL_NOT_VERIFIED"),
)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserOut]:
    """List every user, newest first (admin only)."""
    users = await users_service.list_users(db)
    return [UserOut.model_validate(user) for user in users]


UserId = Annotated[UUID, Path(description="User ID.")]


@router.post(
    "/{user_id}/promote",
    response_model=UserOut,
    dependencies=[Depends(require_verified_user)],
    responses=error_responses(
        "FORBIDDEN",
        "EMAIL_NOT_VERIFIED",
        "USER_NOT_FOUND",
        "VALIDATION_FAILED",
        "CANNOT_MODIFY_OWN_ADMIN",
    ),
)
async def promote_user(
    user_id: UserId,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    """Grant a user admin access (admin only; idempotent)."""
    user = await users_service.promote_admin(db, user_id=user_id, actor=actor)
    return UserOut.model_validate(user)


@router.post(
    "/{user_id}/demote",
    response_model=UserOut,
    dependencies=[Depends(require_verified_user)],
    responses=error_responses(
        "FORBIDDEN",
        "EMAIL_NOT_VERIFIED",
        "USER_NOT_FOUND",
        "VALIDATION_FAILED",
        "CANNOT_MODIFY_OWN_ADMIN",
    ),
)
async def demote_user(
    user_id: UserId,
    actor: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    """Revoke a user's admin access (admin only; idempotent)."""
    user = await users_service.demote_admin(db, user_id=user_id, actor=actor)
    return UserOut.model_validate(user)
