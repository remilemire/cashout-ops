from __future__ import annotations

from collections.abc import Mapping

from app.core.outbox import OutboxMessageDefinition, OutboxMessageDefinitionList
from app.features.auth.outbox import OutboxMessageType as AuthOutboxMessageType
from app.features.auth.outbox import (
    outbox_message_definitions as auth_outbox_message_definitions,
)
from app.features.cashout.outbox import OutboxMessageType as CashoutOutboxMessageType
from app.features.cashout.outbox import (
    outbox_message_definitions as cashout_outbox_message_definitions,
)

type OutboxMessageType = AuthOutboxMessageType | CashoutOutboxMessageType

type OutboxMessageCatalog = Mapping[
    OutboxMessageType, OutboxMessageDefinition[OutboxMessageType]
]

_outbox_message_definitions: OutboxMessageDefinitionList[OutboxMessageType] = [
    *auth_outbox_message_definitions,
    *cashout_outbox_message_definitions,
]


def _build_catalog(
    definitions: OutboxMessageDefinitionList[OutboxMessageType],
) -> OutboxMessageCatalog:
    # Boot-time guard: a type claimed by two features would otherwise be
    # silently last-writer-wins.
    catalog: dict[OutboxMessageType, OutboxMessageDefinition[OutboxMessageType]] = {}
    for definition in definitions:
        if definition.type in catalog:
            raise Exception(
                f'Duplicate outbox message definition for type "{definition.type}".'
            )
        catalog[definition.type] = definition
    return catalog


outbox_message_catalog: OutboxMessageCatalog = _build_catalog(
    _outbox_message_definitions
)

__all__ = ["OutboxMessageType", "outbox_message_catalog"]
