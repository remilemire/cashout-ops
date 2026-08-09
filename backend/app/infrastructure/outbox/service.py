# backend/app/infrastructure/outbox/service.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from .catalog import outbox_message_catalog
from .messages.model import OutboxMessage
from .messages.service import insert_outbox_message


async def enqueue(
    db: AsyncSession,
    *,
    type: str,
    payload: Mapping[str, Any],
    max_attempts: int | None = None,
) -> OutboxMessage:
    """Validate a payload against its definition and persist the message.

    Validation happens here so a payload that doesn't match its cataloged
    schema fails the enqueueing request instead of dead-lettering at
    dispatch. Both raises are programmer errors and deliberately not part of
    the API error contract.
    """
    definition = outbox_message_catalog.get(type)
    if definition is None:
        raise LookupError(f'Unknown outbox message type "{type}".')

    try:
        parsed = definition.payload.model_validate(dict(payload))
    except ValidationError as error:
        # Wrapped so the global pydantic translation cannot present an
        # internal bug as a request validation failure.
        raise ValueError(
            f'Outbox payload for message type "{type}" failed validation: {error}'
        ) from error

    return await insert_outbox_message(
        db, type=type, payload=parsed, max_attempts=max_attempts
    )


__all__ = ["enqueue"]
