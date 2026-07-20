# backend/app/features/invitations/service.py

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.errors import AppError
from app.features.users import service as users_service

from .model import Invitation
from .schemas import InvitationCreate


async def list_invitations(db: AsyncSession) -> Sequence[Invitation]:
    """Every invitation, newest first (admin table)."""
    stmt = select(Invitation).order_by(Invitation.created_at.desc())
    return (await db.execute(stmt)).scalars().all()


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
    db.add(invitation)

    # Flush so the generated id/created_at serialize; a duplicate email raises
    # here and translates to INVITATION_EXISTS via ix_invitations_email. Any
    # prior invitation (even expired or accepted) blocks a new one — delete it
    # first to re-invite.
    await db.flush()

    return invitation


async def is_invited(db: AsyncSession, *, email: str) -> bool:
    """Whether the email holds an unaccepted, unexpired invitation."""
    return await _find_pending(db, email=email) is not None


async def mark_accepted(
    db: AsyncSession, *, email: str, accepted_by_id: UUID
) -> Invitation | None:
    """Consume the email's pending invitation; None if there is none."""
    invitation = await _find_pending(db, email=email)
    if invitation is None:
        return None

    invitation.accepted_by_user_id = accepted_by_id
    invitation.accepted_at = datetime.now(UTC)

    return invitation


async def delete_by_id(db: AsyncSession, *, invitation_id: UUID) -> None:
    invitation = await Invitation.find_by_id(db, invitation_id)
    if invitation is None:
        raise AppError("INVITATION_NOT_FOUND")
    await db.delete(invitation)


async def _find_pending(db: AsyncSession, *, email: str) -> Invitation | None:
    stmt = select(Invitation).where(
        Invitation.email == email,
        Invitation.accepted_at.is_(None),
        Invitation.expires_at > datetime.now(UTC),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


__all__ = ["list_invitations", "create", "is_invited", "mark_accepted", "delete_by_id"]
