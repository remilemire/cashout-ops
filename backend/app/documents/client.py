from __future__ import annotations

from app.integrations.ai import AIClient, ResponseModelT
from app.integrations.storage import DocumentStorageClient

from .schemas import ClassificationT, DocumentClassification
from .types import DocumentRef


class DocumentAIClient:
    """Generic classification and structured extraction for stored documents."""

    def __init__(
        self,
        ai: AIClient,
        storage: DocumentStorageClient,
    ) -> None:
        # TODO(document-ai): Retain the clients and add shared document preparation.
        raise NotImplementedError

    async def classify(
        self,
        document: DocumentRef,
        classification_type: type[ClassificationT],
        *,
        instructions: str | None = None,
    ) -> DocumentClassification[ClassificationT]:
        # TODO(document-ai): Build a typed classification response from the enum.
        raise NotImplementedError

    async def process(
        self,
        document: DocumentRef,
        response_model: type[ResponseModelT],
        *,
        instructions: str | None = None,
    ) -> ResponseModelT:
        # TODO(document-ai): Read the bytes, combine them with the reference's
        # content type, and invoke AIClient.analyze.
        raise NotImplementedError


__all__ = ["DocumentAIClient"]
