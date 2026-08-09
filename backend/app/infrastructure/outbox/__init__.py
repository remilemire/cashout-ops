# backend/app/infrastructure/outbox/__init__.py

from __future__ import annotations

from .contracts import OutboxHandler, OutboxHandlerRegistry, OutboxMessageDefinition
from .dispatcher import OutboxDispatcher
from .messages import OutboxMessage

# `enqueue` and the lifespan helpers are deliberately NOT re-exported here.
# They reach the feature outbox modules through the catalog, while feature
# outbox modules import this package root for the contracts — re-exporting
# them would close that import cycle (a feature module's import triggers this
# __init__ before the feature module has defined its definitions). Import
# them from their submodules instead:
#
#   from app.infrastructure.outbox.service import enqueue
#   from app.infrastructure.outbox.lifespan import (
#       OutboxWorkerPool, create_outbox_handler_registry, outbox_lifespan,
#   )

__all__ = [
    "OutboxDispatcher",
    "OutboxHandler",
    "OutboxHandlerRegistry",
    "OutboxMessage",
    "OutboxMessageDefinition",
]
