# backend/tests/fakes.py

"""In-memory doubles for the AI and storage integrations.

The document-extraction stack (processor, registry, DocumentAIClient) is real in
tests; only the AI *provider* and the object store are faked so tests never make
a network call or touch the filesystem.
"""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel

from app.documents import DocumentClassification
from app.integrations.ai import AIAnalysisError, AIContent, AIProvider, ResponseModelT


def _is_classification(response_model: type[BaseModel]) -> bool:
    try:
        return issubclass(response_model, DocumentClassification)
    except TypeError:
        return False


class FakeAIClient:
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


class FakeDocumentStorage:
    """In-memory `DocumentStorageClient`."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def read(self, storage_key: str) -> bytes:
        return self.objects[storage_key]

    async def write(self, storage_key: str, data: bytes) -> None:
        self.objects[storage_key] = data

    async def delete(self, storage_key: str) -> None:
        self.objects.pop(storage_key, None)
