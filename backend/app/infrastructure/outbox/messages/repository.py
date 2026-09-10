"""Database access for outbox messages; only the outbox package uses this."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .model import OutboxMessage


async def add(db: AsyncSession, message: OutboxMessage) -> None:
    db.add(message)
    await db.flush()


async def find_claimed(
    db: AsyncSession, *, message_id: UUID, claim_id: UUID
) -> OutboxMessage | None:
    """The message, but only while the given claim still owns it.

    Returns None once the lease expired and another worker reclaimed the row,
    so a slow worker cannot overwrite the new owner's outcome.
    """
    stmt = select(OutboxMessage).where(
        OutboxMessage.id == message_id, OutboxMessage.claim_id == claim_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _claimable(now: datetime) -> tuple[ColumnElement[bool], ...]:
    """Not terminal, and not held under a live lease."""
    return (
        OutboxMessage.completed_at.is_(None),
        OutboxMessage.dead_lettered_at.is_(None),
        or_(
            OutboxMessage.lease_expires_at.is_(None),
            OutboxMessage.lease_expires_at <= now,
        ),
    )


def _effective_max_attempts(default_max_attempts: int) -> ColumnElement[int]:
    return func.coalesce(OutboxMessage.max_attempts, default_max_attempts)


async def list_claimable(
    db: AsyncSession,
    *,
    now: datetime,
    default_max_attempts: int,
    batch_size: int,
) -> Sequence[OutboxMessage]:
    """Pending messages ready for a handling attempt, locked for this claim.

    FOR UPDATE SKIP LOCKED keeps concurrent workers from blocking on (or
    double-claiming) the same rows; the caller stamps the lease and commits.
    """
    stmt = (
        select(OutboxMessage)
        .where(
            *_claimable(now),
            OutboxMessage.available_at <= now,
            OutboxMessage.attempts < _effective_max_attempts(default_max_attempts),
        )
        .order_by(OutboxMessage.created_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    return (await db.execute(stmt)).scalars().all()


async def list_exhausted(
    db: AsyncSession,
    *,
    now: datetime,
    default_max_attempts: int,
    batch_size: int,
) -> Sequence[OutboxMessage]:
    """Messages whose attempts ran out, awaiting dead-lettering.

    Deliberately ignores `available_at`: the final failure pushed it forward,
    but there is no point delaying the dead-letter callback.
    """
    stmt = (
        select(OutboxMessage)
        .where(
            *_claimable(now),
            OutboxMessage.attempts >= _effective_max_attempts(default_max_attempts),
        )
        .order_by(OutboxMessage.created_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    return (await db.execute(stmt)).scalars().all()


__all__ = ["add", "find_claimed", "list_claimable", "list_exhausted"]
