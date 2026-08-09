# backend/app/infrastructure/outbox/catalog.py

from __future__ import annotations

from collections.abc import Mapping

from app.features.cashout.outbox import cashout_outbox_message_definitions

from .contracts import OutboxMessageDefinition

outbox_message_definitions = [*cashout_outbox_message_definitions]

type OutboxMessageCatalog = Mapping[str, OutboxMessageDefinition]

outbox_message_catalog: OutboxMessageCatalog = {
    definition.type: definition for definition in outbox_message_definitions
}

__all__ = ["outbox_message_catalog"]
