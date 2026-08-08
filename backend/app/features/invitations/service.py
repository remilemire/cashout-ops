# backend/app/features/invitations/service.py

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import AppError
from app.features.users import service as users_service

from . import repository
from .model import Invitation
from .schemas import InvitationCreate


async def list_invitations(db: AsyncSession) -> Sequence[Invitation]:
    """Every invitation, newest first (admin table)."""
    return await repository.list_all(db)


async def create(
    db: AsyncSession, *, payload: InvitationCreate, invited_by_id: UUID
) -> Invitation:
    if await users_service.find_by_email(db, email=payload.email) is not None:
        raise AppError("EMAIL_TAKEN")

    invitation = Invitation(
        email=payload.email,
        invited_by_user_id=invited_by_id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.INVITATION_TTL_DAYS),
    )
    await repository.add(db, invitation)

    return invitation


async def is_invited(db: AsyncSession, *, email: str) -> bool:
    """Whether the email holds an unaccepted, unexpired invitation."""
    return await repository.find_pending(db, email=email) is not None


async def mark_accepted(
    db: AsyncSession, *, email: str, accepted_by_id: UUID
) -> Invitation | None:
    """Consume the email's pending invitation; None if there is none."""
    invitation = await repository.find_pending(db, email=email)
    if invitation is None:
        return None

    invitation.accepted_by_user_id = accepted_by_id
    invitation.accepted_at = datetime.now(UTC)

    return invitation


async def delete_by_id(db: AsyncSession, *, invitation_id: UUID) -> None:
    invitation = await repository.find_by_id(db, invitation_id=invitation_id)
    if invitation is None:
        raise AppError("INVITATION_NOT_FOUND")
    await repository.delete(db, invitation)


__all__ = ["list_invitations", "create", "is_invited", "mark_accepted", "delete_by_id"]
