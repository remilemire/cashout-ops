# backend/app/documents/client.py

from __future__ import annotations

from app.integrations.ai import AIClient, ResponseModelT, compose_instructions
from app.integrations.storage import DocumentStorageClient
from app.lib.documents import DocumentContent

from .schemas import ClassificationT, DocumentAnalysis, DocumentClassification
from .types import DocumentRef

# Base instructions are always present; a caller's `instructions` are appended
# on top (see compose_instructions), never used as a replacement.
_CLASSIFY_INSTRUCTIONS = (
    "Classify the document as one of the allowed values and report your "
    "confidence between 0 and 1. Choose the value that best matches the "
    "document, and reflect any uncertainty in a lower confidence. If none of "
    "the allowed values apply, leave the value null."
)

_EXTRACT_INSTRUCTIONS = (
    "Extract the requested fields from the document into the given structure. "
    "Report an overall confidence between 0 and 1, and list any fields you were "
    "unsure about or that seemed inconsistent as issues, each with the field "
    "path and a short message."
)


class DocumentAIClient:
    """Generic classification and structured extraction for stored documents."""

    def __init__(
        self,
        ai: AIClient,
        storage: DocumentStorageClient,
    ) -> None:
        self.ai = ai
        self._storage = storage

    async def classify(
        self,
        document: DocumentRef,
        classification_type: type[ClassificationT],
        *,
        instructions: str | None = None,
    ) -> DocumentClassification[ClassificationT]:
        return await self.ai.analyze(
            await self._read(document),
            DocumentClassification[classification_type],
            instructions=compose_instructions(_CLASSIFY_INSTRUCTIONS, instructions),
        )

    async def process(
        self,
        document: DocumentRef,
        response_model: type[ResponseModelT],
        *,
        instructions: str | None = None,
    ) -> DocumentAnalysis[ResponseModelT]:
        return await self.ai.analyze(
            await self._read(document),
            DocumentAnalysis[response_model],
            instructions=compose_instructions(_EXTRACT_INSTRUCTIONS, instructions),
        )

    async def _read(self, document: DocumentRef) -> DocumentContent:
        data = await self._storage.read(document.storage_key)
        return DocumentContent(data=data, content_type=document.content_type)


__all__ = ["DocumentAIClient"]
