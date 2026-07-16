from __future__ import annotations

from typing import Protocol, TypeAlias, TypeVar

from pydantic import BaseModel

from app.lib.documents import DocumentContent

from .types import AIProvider

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)
AIContent: TypeAlias = str | DocumentContent


class AIClient(Protocol):
    """Provider-neutral primitives for structured AI analysis.

    `analyze` raises `AIAnalysisError` on provider failures, refusals, or
    responses that do not validate against `response_model`.
    """

    provider: AIProvider
    model: str

    async def analyze(
        self,
        content: AIContent,
        response_model: type[ResponseModelT],
        *,
        instructions: str | None = None,
    ) -> ResponseModelT: ...


__all__ = ["AIClient", "AIContent", "ResponseModelT"]
