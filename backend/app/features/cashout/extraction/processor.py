from __future__ import annotations

from dataclasses import dataclass

from app.documents import DocumentAIClient, DocumentClassification, DocumentRef

from ..types import CashoutDocumentType
from .schemas import CashoutDocumentSchema


@dataclass(frozen=True)
class CashoutDocumentProcessingResult:
    classification: DocumentClassification[CashoutDocumentType]
    data: CashoutDocumentSchema | None


class CashoutDocumentProcessor:
    """Maps generic document analysis onto the cashout domain."""

    def __init__(self, documents: DocumentAIClient) -> None:
        # TODO(document-ai): Retain the generic document client.
        raise NotImplementedError

    async def process(
        self,
        document: DocumentRef,
    ) -> CashoutDocumentProcessingResult:
        # TODO(document-ai):
        # 1. Classify with CashoutDocumentType.
        # 2. Select its model from CASHOUT_DOCUMENT_SCHEMAS.
        # 3. Invoke DocumentAIClient.process.
        # 4. Add deterministic validation when the schemas are implemented.
        raise NotImplementedError


__all__ = ["CashoutDocumentProcessingResult", "CashoutDocumentProcessor"]
