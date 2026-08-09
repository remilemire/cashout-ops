# backend/app/infrastructure/outbox/lifespan.py

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings

from .catalog import outbox_message_catalog
from .contracts import OutboxHandler, OutboxHandlerRegistry
from .dispatcher import OutboxDispatcher


@dataclass(frozen=True)
class OutboxWorkerPool:
    sessionmaker: async_sessionmaker[AsyncSession]
    registry: OutboxHandlerRegistry
    workers: int = 1


# Boot-time cross-check of handlers against the aggregated definitions, so a
# missing or duplicate handler fails startup instead of dead-lettering
# messages at runtime.
def create_outbox_handler_registry(
    handlers: Sequence[OutboxHandler[Any]],
) -> OutboxHandlerRegistry:
    registry: dict[str, OutboxHandler[Any]] = {}

    for handler in handlers:
        type = handler.message.type

        if type in registry:
            raise Exception(f'Duplicate outbox handler for message type "{type}".')
        if type not in outbox_message_catalog:
            raise Exception(f'Outbox handler for unknown message type "{type}"')

        registry[type] = handler

    for type in outbox_message_catalog:
        if type not in registry:
            raise Exception(f'No outbox handler registered for message type "{type}".')

    return registry


@asynccontextmanager
async def outbox_lifespan(worker_pool: OutboxWorkerPool) -> AsyncGenerator[None]:
    """Run the pool's dispatcher workers for the app's lifetime."""
    dispatchers = [
        OutboxDispatcher(
            worker_pool.sessionmaker,
            worker_pool.registry,
            max_attempts=settings.OUTBOX_MAX_ATTEMPTS,
            batch_size=settings.OUTBOX_BATCH_SIZE,
            poll_interval_s=settings.OUTBOX_POLL_INTERVAL_SECONDS,
            claim_ttl_s=settings.OUTBOX_CLAIM_TTL_SECONDS,
            backoff_base_s=settings.OUTBOX_BACKOFF_BASE_SECONDS,
            backoff_cap_s=settings.OUTBOX_BACKOFF_CAP_SECONDS,
        )
        for _ in range(worker_pool.workers)
    ]
    for dispatcher in dispatchers:
        await dispatcher.start()
    try:
        yield
    finally:
        await asyncio.gather(*(dispatcher.end() for dispatcher in dispatchers))


__all__ = ["OutboxWorkerPool", "create_outbox_handler_registry", "outbox_lifespan"]
