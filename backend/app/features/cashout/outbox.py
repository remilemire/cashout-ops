# backend/app/features/cashout/outbox.py

"""Aggregated outbox surface for the cashout feature.

Message definitions and handlers live with their owning sub-features; this
module only collects and re-exports them for the outbox catalog and the
composition root.
"""

from __future__ import annotations

from app.core.outbox import OutboxMessageDefinitionList

from .analyses.outbox import (
    OutboxMessageType as AnalysesOutboxMessageType,
)
from .analyses.outbox import RunExtractionOutboxHandler
from .analyses.outbox import (
    outbox_message_definitions as analyses_outbox_message_definitions,
)

type OutboxMessageType = AnalysesOutboxMessageType

outbox_message_definitions: OutboxMessageDefinitionList[OutboxMessageType] = [
    *analyses_outbox_message_definitions,
]

__all__ = [
    "OutboxMessageType",
    "RunExtractionOutboxHandler",
    "outbox_message_definitions",
]
