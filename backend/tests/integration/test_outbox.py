# backend/tests/integration/test_outbox.py

"""Outbox behavior against a real database: enqueue, dispatch, retry, dead-letter."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.outbox.contracts import (
    OutboxHandlerRegistry,
    OutboxMessageDefinition,
)
from app.infrastructure.outbox.dispatcher import OutboxDispatcher
from app.infrastructure.outbox.messages.model import OutboxMessage
from app.infrastructure.outbox.messages.service import insert_outbox_message
from app.infrastructure.outbox.service import enqueue

# ================================
# ----------- Fixtures -----------
# ================================


class GreetPayload(BaseModel):
    name: str


# Not in the global catalog: dispatch works from the registry alone, so tests
# can run private message types without touching the feature definitions.
greet_message = OutboxMessageDefinition("test.greet", GreetPayload)


class RecordingHandler:
    message = greet_message

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.handled: list[GreetPayload] = []
        self.dead_lettered: list[GreetPayload] = []

    async def handle(self, payload: GreetPayload) -> None:
        if self.error is not None:
            raise self.error
        self.handled.append(payload)

    async def on_dead_letter(self, payload: GreetPayload) -> None:
        self.dead_lettered.append(payload)


def _dispatcher(
    sessionmaker: async_sessionmaker[AsyncSession], registry: OutboxHandlerRegistry
) -> OutboxDispatcher:
    # Production defaults except the poll interval, kept short so the
    # lifecycle test reacts quickly.
    return OutboxDispatcher(
        sessionmaker,
        registry,
        max_attempts=10,
        batch_size=1,
        poll_interval_s=0.05,
        claim_ttl_s=30.0,
        backoff_base_s=5.0,
        backoff_cap_s=900.0,
    )


async def _insert(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    type: str,
    payload: BaseModel,
    max_attempts: int | None = None,
) -> UUID:
    async with sessionmaker() as db:
        message = await insert_outbox_message(
            db, type=type, payload=payload, max_attempts=max_attempts
        )
        await db.commit()
        return message.id


async def _fetch(
    sessionmaker: async_sessionmaker[AsyncSession], message_id: UUID
) -> OutboxMessage:
    async with sessionmaker() as db:
        message = await db.get(OutboxMessage, message_id)
        assert message is not None
        return message


# ================================
# ------------ Enqueue -----------
# ================================


async def test_enqueue_validates_and_persists_the_message(
    db_session: AsyncSession,
) -> None:
    document_id = uuid4()

    message = await enqueue(
        db_session,
        type="cashout.run_extraction",
        payload={"document_id": str(document_id)},
    )

    assert message.type == "cashout.run_extraction"
    assert message.payload == {"document_id": str(document_id)}
    assert message.attempts == 0


async def test_enqueue_rejects_an_unknown_type(db_session: AsyncSession) -> None:
    with pytest.raises(LookupError, match="Unknown outbox message type"):
        await enqueue(db_session, type="test.not_cataloged", payload={})


async def test_enqueue_rejects_a_payload_that_fails_validation(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(ValueError, match="failed validation"):
        await enqueue(
            db_session,
            type="cashout.run_extraction",
            payload={"document_id": "not-a-uuid"},
        )


# ================================
# ----------- Dispatch -----------
# ================================


async def test_tick_processes_a_pending_message(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    handler = RecordingHandler()
    message_id = await _insert(
        db_sessionmaker, type=greet_message.type, payload=GreetPayload(name="ada")
    )
    dispatcher = _dispatcher(db_sessionmaker, {greet_message.type: handler})

    assert await dispatcher.tick() == 1

    assert [payload.name for payload in handler.handled] == ["ada"]
    message = await _fetch(db_sessionmaker, message_id)
    assert message.completed_at is not None
    assert message.attempts == 1
    assert message.lease_expires_at is None

    # Terminal: the message is never claimed again.
    assert await dispatcher.tick() == 0


async def test_a_failed_attempt_backs_off_and_records_the_error(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    handler = RecordingHandler(error=RuntimeError("smtp down"))
    message_id = await _insert(
        db_sessionmaker, type=greet_message.type, payload=GreetPayload(name="ada")
    )
    dispatcher = _dispatcher(db_sessionmaker, {greet_message.type: handler})

    before = datetime.now(UTC)
    assert await dispatcher.tick() == 1

    message = await _fetch(db_sessionmaker, message_id)
    assert message.completed_at is None
    assert message.dead_lettered_at is None
    assert message.attempts == 1
    # A concise application-level description, not a stack trace.
    assert message.last_error == "RuntimeError: smtp down"
    assert message.claim_id is None
    assert message.available_at > before  # pushed forward by the retry backoff

    # Not eligible again until the backoff elapses, and not dead-lettered.
    assert await dispatcher.tick() == 0
    assert handler.dead_lettered == []


async def test_exhausted_attempts_dead_letter_the_message(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    handler = RecordingHandler(error=RuntimeError("boom"))
    message_id = await _insert(
        db_sessionmaker,
        type=greet_message.type,
        payload=GreetPayload(name="ada"),
        max_attempts=1,
    )
    dispatcher = _dispatcher(db_sessionmaker, {greet_message.type: handler})

    # The single allowed attempt fails; the same tick's sweep dead-letters it.
    assert await dispatcher.tick() == 1

    message = await _fetch(db_sessionmaker, message_id)
    assert message.dead_lettered_at is not None
    assert message.completed_at is None
    assert [payload.name for payload in handler.dead_lettered] == ["ada"]
    assert handler.handled == []

    # Terminal: neither reclaimed nor dead-lettered twice.
    assert await dispatcher.tick() == 0
    assert len(handler.dead_lettered) == 1


async def test_an_unparseable_payload_dead_letters_without_the_callback(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    class WrongPayload(BaseModel):
        count: int

    handler = RecordingHandler()
    message_id = await _insert(
        db_sessionmaker, type=greet_message.type, payload=WrongPayload(count=3)
    )
    dispatcher = _dispatcher(db_sessionmaker, {greet_message.type: handler})

    assert await dispatcher.tick() == 1

    message = await _fetch(db_sessionmaker, message_id)
    assert message.dead_lettered_at is not None
    assert message.last_error is not None
    assert handler.handled == []
    assert handler.dead_lettered == []


async def test_a_message_with_no_handler_dead_letters(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    message_id = await _insert(
        db_sessionmaker, type="test.orphan", payload=GreetPayload(name="ada")
    )
    dispatcher = _dispatcher(db_sessionmaker, {})

    assert await dispatcher.tick() == 1

    message = await _fetch(db_sessionmaker, message_id)
    assert message.dead_lettered_at is not None
    assert message.last_error is not None
    assert "No outbox handler" in message.last_error


# ================================
# ----------- Lifecycle ----------
# ================================


async def test_start_and_end_process_messages_in_the_background(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    handler = RecordingHandler()
    await _insert(
        db_sessionmaker, type=greet_message.type, payload=GreetPayload(name="ada")
    )
    dispatcher = _dispatcher(db_sessionmaker, {greet_message.type: handler})

    await dispatcher.start()
    try:
        async with asyncio.timeout(5):
            while not handler.handled:
                await asyncio.sleep(0.05)
    finally:
        await dispatcher.end()

    assert [payload.name for payload in handler.handled] == ["ada"]
