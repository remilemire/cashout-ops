# backend/app/infrastructure/outbox/lifespan.py

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass

from .catalog import outbox_message_catalog
from .contracts import OutboxHandler, OutboxHandlerRegistry


@dataclass(frozen=True)
class OutboxWorkerPool:
    registry: OutboxHandlerRegistry
    workers: int


# Boot-time cross-check of handlers against the aggregated definitions, so a
# missing or duplicate handler fails startup instead of dead-lettering
# messages at runtime.
def create_outbox_handler_registry(
    handlers: Sequence[OutboxHandler],
) -> OutboxHandlerRegistry:
    registry: dict[str, OutboxHandler] = {}

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


def outbox_lifespan(worker_pool: OutboxWorkerPool) -> AsyncGenerator[None]: ...


__all__ = ["OutboxWorkerPool", "create_outbox_handler_registry", "outbox_lifespan"]
