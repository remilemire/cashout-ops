# backend/app/integrations/ai/client.py

from __future__ import annotations

from typing import Protocol, TypeAlias, TypeVar

from pydantic import BaseModel

from app.core.ai import AIProvider
from app.lib.documents import DocumentContent

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)
AIContent: TypeAlias = str | DocumentContent


class AIClient(Protocol):
    """Provider-neutral primitives for structured AI analysis.

    `analyze` raises `AIAnalysisError` on provider failures, refusals, or
    responses that do not validate against `response_model`. `max_tokens` is
    per-call so callers can budget each operation separately (classification
    needs far fewer output tokens than extraction).
    """

    provider: AIProvider
    model: str

    async def analyze(
        self,
        content: AIContent,
        response_model: type[ResponseModelT],
        *,
        instructions: str | None = None,
        max_tokens: int,
    ) -> ResponseModelT: ...


__all__ = ["AIClient", "AIContent", "ResponseModelT"]
