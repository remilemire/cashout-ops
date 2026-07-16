# backend/app/features/cashout/extraction/processor.py

from __future__ import annotations

from dataclasses import dataclass

from app.documents import (
    DocumentAIClient,
    DocumentClassification,
    DocumentRef,
    FieldIssue,
)
from app.integrations.ai import AIProvider

from ..types import CashoutDocumentType
from .registry import CASHOUT_DOCUMENT_SCHEMAS
from .schemas import CashoutDocumentSchema

_CLASSIFY_INSTRUCTIONS = (
    "You are classifying a document from a restaurant's end-of-shift cashout. "
    "Choose the single best matching document type; use UNKNOWN when no type "
    "clearly applies. Report your confidence between 0 and 1."
)

_EXTRACT_INSTRUCTIONS = (
    "Extract the requested fields from this restaurant cashout document. "
    "Report monetary amounts as plain decimal numbers without currency "
    "symbols, and leave a field null when its value is not present."
)


@dataclass(frozen=True)
class CashoutDocumentProcessingResult:
    classification: DocumentClassification[CashoutDocumentType]
    # data/confidence/issues are None/empty when the document is unclassified.
    data: CashoutDocumentSchema | None
    confidence: float | None
    issues: list[FieldIssue]
    schema_name: str | None


class CashoutDocumentProcessor:
    """Maps generic document analysis onto the cashout domain."""

    def __init__(self, documents: DocumentAIClient) -> None:
        self._documents = documents

    @property
    def provider(self) -> AIProvider:
        return self._documents.ai.provider

    @property
    def model(self) -> str:
        return self._documents.ai.model

    async def process(
        self,
        document: DocumentRef,
    ) -> CashoutDocumentProcessingResult:
        classification = await self._documents.classify(
            document, CashoutDocumentType, instructions=_CLASSIFY_INSTRUCTIONS
        )

        schema = CASHOUT_DOCUMENT_SCHEMAS.get(classification.value)
        if schema is None:
            return CashoutDocumentProcessingResult(
                classification=classification,
                data=None,
                confidence=None,
                issues=[],
                schema_name=None,
            )

        # TODO(document-ai): Add deterministic validation once the schemas
        # define real fields (totals reconcile, amounts non-negative, ...).
        analysis = await self._documents.process(
            document, schema, instructions=_EXTRACT_INSTRUCTIONS
        )
        return CashoutDocumentProcessingResult(
            classification=classification,
            data=analysis.data,
            confidence=analysis.confidence,
            issues=analysis.issues,
            schema_name=schema.__name__,
        )


__all__ = ["CashoutDocumentProcessingResult", "CashoutDocumentProcessor"]
