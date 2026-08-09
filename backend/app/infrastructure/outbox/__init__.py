# backend/app/infrastructure/outbox/__init__.py

from __future__ import annotations

from .contracts import OutboxMessageDefinition
from .lifespan import create_outbox_handler_registry, outbox_lifespan
from .messages import OutboxMessage
from .service import enqueue

__all__ = [
    "enqueue",
    "OutboxMessageDefinition",
    "create_outbox_handler_registry",
    "outbox_lifespan",
    "OutboxMessage",
]
