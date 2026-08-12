# backend/app/lifespan.py

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.document_ai import DocumentAIClient
from app.features.auth.outbox import SendLoginLinkEmailOutboxHandler
from app.features.cashout.extraction import CashoutDocumentProcessor
from app.features.cashout.outbox import RunExtractionOutboxHandler
from app.infrastructure.db.lifespan import db_lifespan
from app.infrastructure.outbox.lifespan import (
    OutboxWorkerPool,
    create_outbox_handler_registry,
    outbox_lifespan,
)
from app.infrastructure.redis.lifespan import redis_lifespan
from app.integrations.ai.lifespan import ai_lifespan
from app.integrations.email.lifespan import email_lifespan
from app.integrations.storage.lifespan import storage_lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Composition root: orchestrates the per-component lifespans.

    Each component lifespan builds and tears down its own resources; this is
    the only place that wires them together and writes to `app.state`.
    """

    async with AsyncExitStack() as stack:
        db = await stack.enter_async_context(db_lifespan())
        redis_client = await stack.enter_async_context(redis_lifespan())
        ai_client = await stack.enter_async_context(ai_lifespan())
        email_client = await stack.enter_async_context(email_lifespan())
        storage = await stack.enter_async_context(storage_lifespan())

        processor = CashoutDocumentProcessor(
            DocumentAIClient(
                ai_client,
                storage,
                classification_max_tokens=settings.ai.CLASSIFICATION_MAX_TOKENS,
                extraction_max_tokens=settings.ai.EXTRACTION_MAX_TOKENS,
            )
        )

        app.state.db_engine = db.engine
        app.state.db_sessionmaker = db.sessionmaker
        app.state.redis = redis_client
        app.state.email_client = email_client
        app.state.document_storage = storage
        app.state.cashout_document_processor = processor

        # Entered last so the dispatchers stop before their dependencies are
        # torn down on shutdown (the exit stack unwinds in reverse).
        registry = create_outbox_handler_registry(
            [
                SendLoginLinkEmailOutboxHandler(
                    db.sessionmaker, redis_client, email_client
                ),
                RunExtractionOutboxHandler(db.sessionmaker, processor),
            ]
        )
        await stack.enter_async_context(
            outbox_lifespan(
                OutboxWorkerPool(sessionmaker=db.sessionmaker, registry=registry)
            )
        )

        yield
