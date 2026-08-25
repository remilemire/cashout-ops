# backend/app/features/users/router.py

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import error_responses
from app.features.auth.dependencies import (
    get_current_user,
    require_admin,
    require_owner,
)
from app.infrastructure.db.dependencies import get_db
from app.security.dependencies import require_csrf

from . import service as users_service
from .model import User
from .schemas import UserCreate, UserOut, UserUpdate

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
    dependencies=[Depends(require_admin)],
    responses=error_responses("FORBIDDEN"),
)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserOut]:
    """List every user, newest first (admin only)."""
    users = await users_service.list_users(db)
    return [UserOut.model_validate(user) for user in users]


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
    responses=error_responses("FORBIDDEN", "EMAIL_TAKEN", "VALIDATION_FAILED"),
)
async def create_user(
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    """Create a staff account (admin only).

    The new user signs in via an emailed login link — there is no password,
    and no email is sent at creation time.
    """
    user = await users_service.create(db, payload=payload)
    return UserOut.model_validate(user)


UserId = Annotated[UUID, Path(description="User ID.")]


@router.patch(
    "/{user_id}",
    response_model=UserOut,
    dependencies=[Depends(require_admin)],
    responses=error_responses("FORBIDDEN", "USER_NOT_FOUND", "VALIDATION_FAILED"),
)
async def update_user(
    user_id: UserId,
    payload: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    """Update a user's name (admin only).

    Any account can be renamed, the owner's and the caller's own included:
    a name carries no privileges.
    """
    user = await users_service.update(db, user_id=user_id, payload=payload)
    return UserOut.model_validate(user)


@router.post(
    "/{user_id}/promote",
    response_model=UserOut,
    responses=error_responses(
        "FORBIDDEN",
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
    responses=error_responses(
        "FORBIDDEN",
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


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
    responses=error_responses(
        "FORBIDDEN",
        "USER_NOT_FOUND",
        "CANNOT_DELETE_OWNER",
        "VALIDATION_FAILED",
    ),
)
async def delete_user(
    user_id: UserId,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a user (admin only): the account is always deactivated.

    The account disappears from listings and can no longer sign in — its
    sessions are not revoked; the deleted-user lookup during authentication
    turns them away — while cashout history keeps its user. The owner cannot
    be deleted; recreating a deleted user's email revives the account as
    staff.
    """
    await users_service.delete_by_id(db, user_id=user_id)


@router.post(
    "/{user_id}/transfer-ownership",
    response_model=UserOut,
    responses=error_responses(
        "FORBIDDEN",
        "USER_NOT_FOUND",
        "TRANSFER_TARGET_NOT_ADMIN",
        "VALIDATION_FAILED",
    ),
)
async def transfer_ownership(
    user_id: UserId,
    actor: Annotated[User, Depends(require_owner)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    """Transfer ownership to an admin (owner only); returns the new owner."""
    user = await users_service.transfer_ownership(db, actor=actor, new_owner_id=user_id)
    return UserOut.model_validate(user)
