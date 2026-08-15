# backend/tests/support/fixtures/outbox.py

"""On-demand outbox delivery over the real handlers and fake clients.

ASGITransport never runs the app lifespan, so no dispatcher polls during
tests; requests only enqueue rows. `drain_outbox` runs dispatcher ticks
until no claimable work remains, standing in for the worker pool.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.auth.outbox import SendLoginLinkEmailOutboxHandler
from app.features.cashout.outbox import RunExtractionOutboxHandler
from app.infrastructure.outbox.dispatcher import OutboxDispatcher
from app.infrastructure.outbox.lifespan import create_outbox_handler_registry
from app.infrastructure.redis import Redis

from ..fakes import FakeAIClient, FakeDocumentStorage, FakeEmailClient


class OutboxDrain:
    """Callable that ticks the dispatcher until the outbox has no ready work."""

    def __init__(self, dispatcher: OutboxDispatcher) -> None:
        self._dispatcher = dispatcher

    async def __call__(self) -> int:
        total = 0
        while claimed := await self._dispatcher.tick():
            total += claimed
        return total


@pytest.fixture
def drain_outbox(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    email_client: FakeEmailClient,
    ai_client: FakeAIClient,
    storage: FakeDocumentStorage,
) -> OutboxDrain:
    # The handler builds its own processor, so it is wired from the same fake
    # AI and storage fixtures the request path uses — tests that configure
    # `ai_client` still steer what the drained extraction returns.
    registry = create_outbox_handler_registry(
        [
            SendLoginLinkEmailOutboxHandler(
                db_sessionmaker, redis_client, email_client
            ),
            RunExtractionOutboxHandler(db_sessionmaker, ai_client, storage),
        ]
    )
    dispatcher = OutboxDispatcher(
        db_sessionmaker,
        registry,
        max_attempts=10,
        batch_size=10,
        poll_interval_s=0.05,
        claim_ttl_s=30.0,
        backoff_base_s=5.0,
        backoff_cap_s=900.0,
    )
    return OutboxDrain(dispatcher)


__all__ = ["OutboxDrain", "drain_outbox"]
