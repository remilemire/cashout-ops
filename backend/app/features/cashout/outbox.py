# backend/app/features/cashout/outbox.py

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.outbox import (
    OutboxMessageDefinition,
)


class _ExampleSchema(BaseModel):
    name: str


_example_outbox_message_definition = OutboxMessageDefinition(
    "cashout.example", _ExampleSchema
)

cashout_outbox_message_definitions = [_example_outbox_message_definition]


class ExampleOutboxHandler:
    message = _example_outbox_message_definition

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]):
        self.sessionmaker = sessionmaker

    async def handler(self, payload: _ExampleSchema) -> None:
        print(payload.name + " handled")

    async def on_dead_letter(self, payload: _ExampleSchema) -> None:
        print(payload.name + " dead")


__all__ = ["cashout_outbox_message_definitions", "ExampleOutboxHandler"]
