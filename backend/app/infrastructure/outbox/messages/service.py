from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from . import repository
from .model import OutboxMessage


async def insert_outbox_message(
    db: AsyncSession,
    *,
    type: str,
    payload: BaseModel,
    max_attempts: int | None = None,
) -> OutboxMessage:
    """Persist a message inside the caller's transaction.

    This is the transactional half of the outbox: the row commits (or rolls
    back) atomically with the caller's other writes. `max_attempts` of None
    defers to the dispatcher's configured default.
    """
    message = OutboxMessage(
        type=type,
        payload=payload.model_dump(mode="json"),
        max_attempts=max_attempts,
    )
    await repository.add(db, message)
    return message


__all__ = ["insert_outbox_message"]
