# backend/app/infrastructure/outbox/catalog.py

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.features.auth.outbox import auth_outbox_message_definitions
from app.features.cashout.outbox import cashout_outbox_message_definitions

from .contracts import OutboxMessageDefinition

outbox_message_definitions: list[OutboxMessageDefinition] = [
    *auth_outbox_message_definitions,
    *cashout_outbox_message_definitions,
]

type OutboxMessageCatalog = Mapping[str, OutboxMessageDefinition]


def _build_catalog(
    definitions: Sequence[OutboxMessageDefinition],
) -> OutboxMessageCatalog:
    # Boot-time guard: a type claimed by two features would otherwise be
    # silently last-writer-wins.
    catalog: dict[str, OutboxMessageDefinition] = {}
    for definition in definitions:
        if definition.type in catalog:
            raise Exception(
                f'Duplicate outbox message definition for type "{definition.type}".'
            )
        catalog[definition.type] = definition
    return catalog


outbox_message_catalog: OutboxMessageCatalog = _build_catalog(
    outbox_message_definitions
)

__all__ = ["outbox_message_catalog"]
