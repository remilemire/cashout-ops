# backend/app/infrastructure/outbox/dispatcher.py

from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .contracts import OutboxHandler, OutboxHandlerRegistry
from .messages import repository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Claimed:
    """Snapshot of a claimed row, safe to use outside the claim transaction."""

    id: UUID
    type: str
    payload: dict[str, Any]
    attempts: int


class OutboxDispatcher:
    """Polls outbox_messages and runs the registered handler for each row.

    Claims are lease-based: the claim transaction stamps `claim_id` and
    `lease_expires_at` (and counts the attempt), the handler then runs outside
    any transaction, and the outcome is recorded in a second transaction
    guarded by the claim id. A worker that crashes mid-message simply lets its
    lease expire, after which the row is claimable again — delivery is
    at-least-once and handlers must tolerate replays.

    A message whose attempts run out is dead-lettered: `on_dead_letter` runs
    once (also at-least-once) and `dead_lettered_at` makes the row terminal.
    A message with no registered handler or an unparseable payload is
    dead-lettered immediately — retrying cannot fix either — without the
    callback, which requires a handler and a parsed payload.
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        registry: OutboxHandlerRegistry,
        *,
        max_attempts: int,
        batch_size: int,
        poll_interval_s: float,
        claim_ttl_s: float,
        backoff_base_s: float,
        backoff_cap_s: float,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._registry = registry
        self._max_attempts = max_attempts
        self._batch_size = batch_size
        self._poll_interval_s = poll_interval_s
        self._claim_ttl_s = claim_ttl_s
        self._backoff_base_s = backoff_base_s
        self._backoff_cap_s = backoff_cap_s
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Begin polling in a background task; idempotent."""
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def end(self) -> None:
        """Stop polling once the in-flight tick finishes; idempotent."""
        if self._task is None:
            return
        self._stop.set()
        await self._task
        self._task = None

    async def tick(self) -> int:
        """One dispatch pass: claim a batch, process it, sweep dead letters.

        Returns the number of messages claimed for handling, so the poll loop
        (and tests) can tell a busy pass from an idle one.
        """
        claim_id, claimed = await self._claim()
        for message in claimed:
            await self._process(claim_id, message)
        await self._sweep_dead_letters()
        return len(claimed)

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                claimed = await self.tick()
            except Exception:
                # Swallow so a transient failure (e.g. a database outage)
                # doesn't kill the poll loop.
                logger.exception("Outbox dispatch tick failed")
                claimed = 0

            if claimed >= self._batch_size:
                continue  # backlog: drain without sleeping
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval_s)
            except TimeoutError:
                pass

    # ================================
    # ---------- Processing ----------
    # ================================

    async def _claim(self) -> tuple[UUID, list[_Claimed]]:
        now = datetime.now(UTC)
        claim_id = uuid4()

        async with self._sessionmaker() as db:
            messages = await repository.list_claimable(
                db,
                now=now,
                default_max_attempts=self._max_attempts,
                batch_size=self._batch_size,
            )
            claimed: list[_Claimed] = []
            for message in messages:
                message.claim_id = claim_id
                message.lease_expires_at = now + timedelta(seconds=self._claim_ttl_s)
                message.attempts += 1
                claimed.append(
                    _Claimed(
                        id=message.id,
                        type=message.type,
                        payload=message.payload,
                        attempts=message.attempts,
                    )
                )
            await db.commit()

        return claim_id, claimed

    async def _process(self, claim_id: UUID, message: _Claimed) -> None:
        handler = self._registry.get(message.type)
        if handler is None:
            # Deploy skew: a row enqueued for a type this build no longer
            # serves. Retrying cannot help.
            logger.error('No outbox handler for message type "%s"', message.type)
            await self._finalize_dead_letter(
                claim_id,
                message.id,
                error=f'No outbox handler registered for message type "{message.type}".',
            )
            return

        try:
            payload = handler.message.payload.model_validate(message.payload)
        except ValidationError:
            logger.exception(
                'Outbox payload for message type "%s" no longer parses', message.type
            )
            await self._finalize_dead_letter(
                claim_id, message.id, error=traceback.format_exc()
            )
            return

        try:
            await handler.handle(payload)
        except Exception:
            logger.exception(
                'Outbox handler for message type "%s" failed (attempt %d)',
                message.type,
                message.attempts,
            )
            await self._finalize_failure(
                claim_id, message, error=traceback.format_exc()
            )
        else:
            await self._finalize_success(claim_id, message.id)

    async def _sweep_dead_letters(self) -> None:
        """Dead-letter messages whose attempts ran out.

        Runs as a claim of its own (rather than inside the failure path) so
        rows orphaned by a crashed worker's final attempt are dead-lettered
        too, not only ones whose last failure happened in this process.
        """
        now = datetime.now(UTC)
        claim_id = uuid4()

        async with self._sessionmaker() as db:
            messages = await repository.list_exhausted(
                db,
                now=now,
                default_max_attempts=self._max_attempts,
                batch_size=self._batch_size,
            )
            exhausted: list[_Claimed] = []
            for message in messages:
                message.claim_id = claim_id
                message.lease_expires_at = now + timedelta(seconds=self._claim_ttl_s)
                exhausted.append(
                    _Claimed(
                        id=message.id,
                        type=message.type,
                        payload=message.payload,
                        attempts=message.attempts,
                    )
                )
            await db.commit()

        for message in exhausted:
            await self._dead_letter(claim_id, message)

    async def _dead_letter(self, claim_id: UUID, message: _Claimed) -> None:
        handler = self._registry.get(message.type)
        if handler is not None:
            payload = self._parse_for_dead_letter(handler, message)
            if payload is not None:
                try:
                    await handler.on_dead_letter(payload)
                except Exception:
                    # The row still becomes terminal: a broken callback must
                    # not keep the sweep re-claiming the message forever.
                    logger.exception(
                        'Outbox dead-letter callback for message type "%s" failed',
                        message.type,
                    )

        logger.error(
            'Outbox message %s of type "%s" dead-lettered after %d attempt(s)',
            message.id,
            message.type,
            message.attempts,
        )
        await self._finalize_dead_letter(claim_id, message.id, error=None)

    def _parse_for_dead_letter(
        self, handler: OutboxHandler[Any], message: _Claimed
    ) -> BaseModel | None:
        try:
            return handler.message.payload.model_validate(message.payload)
        except ValidationError:
            logger.exception(
                'Outbox payload for message type "%s" no longer parses; '
                "dead-lettering without the callback",
                message.type,
            )
            return None

    # ================================
    # ----------- Outcomes -----------
    # ================================

    async def _finalize_success(self, claim_id: UUID, message_id: UUID) -> None:
        async with self._sessionmaker() as db:
            message = await repository.find_claimed(
                db, message_id=message_id, claim_id=claim_id
            )
            if message is None:  # lease expired; another worker owns the row now
                return
            message.completed_at = datetime.now(UTC)
            message.lease_expires_at = None
            await db.commit()

    async def _finalize_failure(
        self, claim_id: UUID, claimed: _Claimed, *, error: str
    ) -> None:
        async with self._sessionmaker() as db:
            message = await repository.find_claimed(
                db, message_id=claimed.id, claim_id=claim_id
            )
            if message is None:
                return
            message.last_error = error
            message.claim_id = None
            message.lease_expires_at = None
            backoff_s = min(
                self._backoff_cap_s,
                self._backoff_base_s * 2 ** (claimed.attempts - 1),
            )
            message.available_at = datetime.now(UTC) + timedelta(seconds=backoff_s)
            await db.commit()

    async def _finalize_dead_letter(
        self, claim_id: UUID, message_id: UUID, *, error: str | None
    ) -> None:
        async with self._sessionmaker() as db:
            message = await repository.find_claimed(
                db, message_id=message_id, claim_id=claim_id
            )
            if message is None:
                return
            message.dead_lettered_at = datetime.now(UTC)
            message.lease_expires_at = None
            if error is not None:
                message.last_error = error
            await db.commit()


__all__ = [
    "OutboxDispatcher",
]
