# backend/app/features/invitations/repository.py

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .model import Invitation


async def list_all(db: AsyncSession) -> Sequence[Invitation]:
    stmt = select(Invitation).order_by(Invitation.created_at.desc())
    return (await db.execute(stmt)).scalars().all()


async def add(db: AsyncSession, invitation: Invitation) -> None:
    db.add(invitation)

    # Flush so the generated id/created_at serialize; a duplicate email raises
    # here and translates to INVITATION_EXISTS via ix_invitations_email. Any
    # prior invitation (even expired or accepted) blocks a new one — delete it
    # first to re-invite.
    await db.flush()


async def find_pending(db: AsyncSession, *, email: str) -> Invitation | None:
    stmt = select(Invitation).where(
        Invitation.email == email,
        Invitation.accepted_at.is_(None),
        Invitation.expires_at > datetime.now(UTC),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def find_by_id(db: AsyncSession, *, invitation_id: UUID) -> Invitation | None:
    return await db.get(Invitation, invitation_id)


async def delete(db: AsyncSession, invitation: Invitation) -> None:
    await db.delete(invitation)


__all__ = ["list_all", "add", "find_pending", "find_by_id", "delete"]
