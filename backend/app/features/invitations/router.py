# backend/app/features/invitations/router.py

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_current_user,
    get_db,
    require_admin,
    require_csrf,
    require_verified_user,
)
from app.errors.openapi import error_responses
from app.features.users.model import User

from . import service as invitations_service
from .schemas import InvitationCreate, InvitationOut

router = APIRouter(
    prefix="/invitations",
    tags=["invitations"],
    dependencies=[
        Depends(require_csrf),
        Depends(require_verified_user),
        Depends(require_admin),
    ],
    responses=error_responses(
        "UNAUTHENTICATED",
        "INVALID_SESSION",
        "INVALID_CSRF_TOKEN",
        "FORBIDDEN",
        "EMAIL_NOT_VERIFIED",
    ),
)

InvitationId = Annotated[UUID, Path(description="Invitation ID.")]


@router.get("", response_model=list[InvitationOut])
async def list_invitations(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[InvitationOut]:
    """List every invitation, newest first (admin only)."""
    invitations = await invitations_service.list_invitations(db)
    return [InvitationOut.model_validate(invitation) for invitation in invitations]


@router.post(
    "",
    response_model=InvitationOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses("EMAIL_TAKEN", "INVITATION_EXISTS", "VALIDATION_FAILED"),
)
async def create_invitation(
    payload: InvitationCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> InvitationOut:
    """Invite an email to register (admin only).

    The invitation expires after `INVITATION_TTL_DAYS`. An email with an
    existing invitation (pending, accepted, or expired) or a registered
    account cannot be re-invited — delete the old invitation first.
    """
    invitation = await invitations_service.create(
        db, payload=payload, invited_by_id=current_user.id
    )
    return InvitationOut.model_validate(invitation)


@router.delete(
    "/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses("INVITATION_NOT_FOUND", "VALIDATION_FAILED"),
)
async def delete_invitation(
    invitation_id: InvitationId,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revoke an invitation (admin only)."""
    await invitations_service.delete_by_id(db, invitation_id=invitation_id)
