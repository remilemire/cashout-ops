# backend/tests/support/fakes/ai.py

from __future__ import annotations

from typing import cast

from pydantic import BaseModel

from app.document_ai import DocumentClassification
from app.integrations.ai import (
    AIAnalysisError,
    AIClient,
    AIContent,
    AIProvider,
    ResponseModelT,
)


def _is_classification(response_model: type[BaseModel]) -> bool:
    try:
        return issubclass(response_model, DocumentClassification)
    except TypeError:
        return False


class FakeAIClient(AIClient):
    """`AIClient` that returns canned structured output (or raises)."""

    # Must be a real AIProvider member: the value flows through the processor
    # into CashoutDocumentAnalysis.provider, a native Postgres enum column, so
    # a made-up "FAKE" value would fail to persist. ANTHROPIC is arbitrary.
    provider: AIProvider = AIProvider.ANTHROPIC

    def __init__(
        self,
        *,
        model: str = "fake-model",
        classification: BaseModel | None = None,
        extraction: BaseModel | None = None,
        error: AIAnalysisError | None = None,
    ) -> None:
        self.model = model
        self.classification = classification
        self.extraction = extraction
        self.error = error
        self.calls: list[tuple[AIContent, type[BaseModel], str | None, int]] = []

    async def analyze(
        self,
        content: AIContent,
        response_model: type[ResponseModelT],
        *,
        instructions: str | None = None,
        max_tokens: int,
    ) -> ResponseModelT:
        self.calls.append((content, response_model, instructions, max_tokens))

        if self.error is not None:
            raise self.error

        result = (
            self.classification
            if _is_classification(response_model)
            else self.extraction
        )
        if result is None:
            raise AssertionError(
                f"FakeAIClient has no configured response for {response_model!r}"
            )
        return cast(ResponseModelT, result)
