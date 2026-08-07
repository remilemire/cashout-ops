# backend/tests/support/fixtures/app.py

"""A fresh FastAPI application per test, with every external seam overridden."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dependencies import (
    get_cashout_document_processor,
    get_db,
    get_db_sessionmaker,
    get_document_storage,
    get_email_client,
    get_redis,
)
from app.features.cashout.extraction import CashoutDocumentProcessor
from app.infrastructure.redis import Redis
from app.main import create_app

from ..fakes import FakeDocumentStorage, FakeEmailClient


@pytest.fixture
def app(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    processor: CashoutDocumentProcessor,
    storage: FakeDocumentStorage,
    email_client: FakeEmailClient,
) -> FastAPI:
    """A per-test app instance (never the app.main singleton, so tests cannot
    leak state into each other). ASGITransport does not run the lifespan, so
    no real engine or provider client is ever constructed."""

    async def _get_db() -> AsyncIterator[AsyncSession]:
        async with db_sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    application = create_app()
    application.dependency_overrides[get_db] = _get_db
    # Background tasks (document extraction) build their own session from this.
    application.dependency_overrides[get_db_sessionmaker] = lambda: db_sessionmaker
    application.dependency_overrides[get_cashout_document_processor] = lambda: processor
    application.dependency_overrides[get_document_storage] = lambda: storage
    application.dependency_overrides[get_email_client] = lambda: email_client
    application.dependency_overrides[get_redis] = lambda: redis_client
    return application
