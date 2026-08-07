# backend/app/lifespan.py

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.documents import DocumentAIClient
from app.features.cashout.extraction import CashoutDocumentProcessor
from app.infrastructure.db.lifespan import db_lifespan
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
        ai_client = await stack.enter_async_context(ai_lifespan())
        email_client = await stack.enter_async_context(email_lifespan())
        storage = await stack.enter_async_context(storage_lifespan())

        app.state.db_engine = db.engine
        app.state.db_sessionmaker = db.sessionmaker
        app.state.email_client = email_client
        app.state.document_storage = storage
        app.state.cashout_document_processor = CashoutDocumentProcessor(
            DocumentAIClient(
                ai_client,
                storage,
                classification_max_tokens=settings.AI_CLASSIFICATION_MAX_TOKENS,
                extraction_max_tokens=settings.AI_EXTRACTION_MAX_TOKENS,
            )
        )

        yield
