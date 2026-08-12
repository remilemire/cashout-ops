# backend/tests/unit/test_outbox.py

"""Boot-time validation of the outbox handler registry against the catalog."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from app.core.outbox import OutboxHandler, OutboxMessageDefinition
from app.infrastructure.outbox.catalog import outbox_message_catalog
from app.infrastructure.outbox.lifespan import create_outbox_handler_registry


def _handler_for(definition: OutboxMessageDefinition) -> OutboxHandler[Any]:
    class _Handler:
        message = definition

        async def handle(self, payload: BaseModel) -> None: ...

        async def on_dead_letter(self, payload: BaseModel) -> None: ...

    return _Handler()


def _full_handler_set() -> list[OutboxHandler[Any]]:
    return [_handler_for(definition) for definition in outbox_message_catalog.values()]


def test_accepts_a_handler_per_cataloged_definition() -> None:
    registry = create_outbox_handler_registry(_full_handler_set())

    assert set(registry) == set(outbox_message_catalog)


def test_rejects_a_missing_handler() -> None:
    handlers = _full_handler_set()[1:]

    with pytest.raises(Exception, match="No outbox handler registered"):
        create_outbox_handler_registry(handlers)


def test_rejects_a_duplicate_handler() -> None:
    handlers = _full_handler_set()

    with pytest.raises(Exception, match="Duplicate outbox handler"):
        create_outbox_handler_registry([*handlers, handlers[0]])


def test_rejects_a_handler_for_an_unknown_type() -> None:
    class _Payload(BaseModel):
        pass

    unknown = OutboxMessageDefinition("test.unknown", _Payload)

    with pytest.raises(Exception, match="unknown message type"):
        create_outbox_handler_registry([*_full_handler_set(), _handler_for(unknown)])
