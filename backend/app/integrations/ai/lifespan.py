# backend/app/integrations/ai/lifespan.py

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from anthropic import AsyncAnthropic
from google import genai
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.providers import AIProvider

from .anthropic import AnthropicAIClient
from .client import AIClient
from .gemini import GeminiAIClient
from .openai import OpenAIAIClient


@asynccontextmanager
async def ai_lifespan() -> AsyncGenerator[AIClient]:
    """Build the configured provider's AI client; close it on exit."""
    client, close = _build_ai_client()
    try:
        yield client
    finally:
        await close()


def _build_ai_client() -> tuple[AIClient, Callable[[], Awaitable[None]]]:
    """Construct the configured provider's client + an async close callback.

    Settings already rejects a model whose provider has no API key, so
    `_require_key` narrows those optional fields for the type checker rather
    than enforcing the requirement itself.
    """
    model = settings.ai.MODEL

    if settings.ai.PROVIDER is AIProvider.OPENAI:
        client = AsyncOpenAI(api_key=_require_key(settings.ai.OPENAI_API_KEY, "OPENAI"))
        return OpenAIAIClient(client, model=model), client.close

    if settings.ai.PROVIDER is AIProvider.GEMINI:
        gemini = genai.Client(
            api_key=_require_key(settings.ai.GEMINI_API_KEY, "GEMINI")
        )

        async def close_gemini() -> None:
            gemini.close()

        return GeminiAIClient(gemini, model=model), close_gemini

    anthropic = AsyncAnthropic(
        api_key=_require_key(settings.ai.ANTHROPIC_API_KEY, "ANTHROPIC")
    )
    return AnthropicAIClient(anthropic, model=model), anthropic.close


def _require_key(value: str | None, provider: str) -> str:
    if not value:
        raise RuntimeError(
            f"{provider}_API_KEY is required when AI_MODEL is served by {provider}."
        )
    return value
