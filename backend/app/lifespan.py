# backend/app/lifespan.py

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from anthropic import AsyncAnthropic
from fastapi import FastAPI
from google import genai
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.documents import DocumentAIClient
from app.features.cashout.extraction import CashoutDocumentProcessor
from app.integrations.ai import (
    AIClient,
    AIProvider,
    AnthropicAIClient,
    GeminiAIClient,
    OpenAIAIClient,
)
from app.integrations.email import (
    ConsoleEmailClient,
    EmailClient,
    EmailProvider,
    ResendEmailClient,
)
from app.integrations.storage import LocalDocumentStorageClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Composition root: builds the DB engine and the integration clients."""

    app.state.db_engine = create_async_engine(settings.DATABASE_URL)
    app.state.db_sessionmaker = async_sessionmaker(
        bind=app.state.db_engine, class_=AsyncSession, expire_on_commit=False
    )

    ai_client, close_ai = _build_ai_client()
    storage = LocalDocumentStorageClient(settings.DOCUMENT_STORAGE_DIR)

    app.state.email_client = _build_email_client()
    app.state.document_storage = storage
    app.state.cashout_document_processor = CashoutDocumentProcessor(
        DocumentAIClient(
            ai_client,
            storage,
            classification_max_tokens=settings.AI_CLASSIFICATION_MAX_TOKENS,
            extraction_max_tokens=settings.AI_EXTRACTION_MAX_TOKENS,
        )
    )

    try:
        yield
    finally:
        await close_ai()
        await app.state.db_engine.dispose()


def _build_email_client() -> EmailClient:
    """Select the configured email client; Resend requires its API key."""
    if settings.EMAIL_PROVIDER is EmailProvider.RESEND:
        if not settings.RESEND_API_KEY:
            raise RuntimeError(
                "RESEND_API_KEY is required when EMAIL_PROVIDER is RESEND."
            )
        return ResendEmailClient(
            api_key=settings.RESEND_API_KEY, sender=settings.EMAIL_FROM
        )
    return ConsoleEmailClient(sender=settings.EMAIL_FROM)


def _build_ai_client() -> tuple[AIClient, Callable[[], Awaitable[None]]]:
    """Construct the configured provider's client + an async close callback."""
    model = settings.AI_MODEL

    if settings.AI_PROVIDER is AIProvider.OPENAI:
        client = AsyncOpenAI(api_key=_require_key(settings.OPENAI_API_KEY, "OPENAI"))
        return OpenAIAIClient(client, model=model), client.close

    if settings.AI_PROVIDER is AIProvider.GEMINI:
        gemini = genai.Client(api_key=_require_key(settings.GEMINI_API_KEY, "GEMINI"))

        async def close_gemini() -> None:
            gemini.close()

        return GeminiAIClient(gemini, model=model), close_gemini

    anthropic = AsyncAnthropic(
        api_key=_require_key(settings.ANTHROPIC_API_KEY, "ANTHROPIC")
    )
    return AnthropicAIClient(anthropic, model=model), anthropic.close


def _require_key(value: str | None, provider: str) -> str:
    if not value:
        raise RuntimeError(
            f"{provider}_API_KEY is required when AI_PROVIDER is {provider}."
        )
    return value
