# backend/app/features/cashout/extraction/processor.py

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.core.providers import AIProvider
from app.document_ai import (
    DocumentAIClient,
    DocumentRef,
    FieldIssue,
)
from app.integrations.ai import AIClient
from app.integrations.storage import DocumentStorageClient

from .registry import CASHOUT_CLASSIFICATION_HINTS, CASHOUT_DOCUMENT_SCHEMAS
from .schemas import CashoutDocumentSchema
from .types import CashoutDocumentClassification

# Per-type signals live in CASHOUT_CLASSIFICATION_HINTS; this keeps only the
# framing, the cross-type distinctions, and the unknown guidance (markers can't
# describe "none of the above").
_CLASSIFY_INSTRUCTIONS = """
The document is one end-of-shift record from a restaurant cashout.

Use unknown for anything else, including unrelated photos and documents too degraded to identify.

Distinguish carefully:

* A touchbistro_report is the point-of-sale end-of-day report, organized around sales categories and payment totals; a server_summary_report is the payment-terminal summary, organized around card transaction counts and totals.
* Both cover the same shift and repeat similar amounts, so classify on the document's own layout and headings rather than on the values it reports.
"""

_EXTRACT_INSTRUCTIONS = """
The document is part of a restaurant cashout / end-of-shift reconciliation: a point-of-sale end-of-day report or a payment-terminal server summary. Similar values may repeat across sections. Read the area relevant to each requested field rather than the document in full.

Interpret fields by their accounting meaning and keep distinct concepts distinct — gross vs. net vs. total sales, individual tenders, collected vs. declared tips, tip-outs, refunds/voids/discounts, expected vs. submitted vs. owed vs. due cash, shortages vs. overages, transaction vs. settlement totals, and subtotal vs. tax vs. tip vs. final charged amount. Do not combine values from different documents or sections, and do not assume two similarly named totals represent the same accounting value.

For monetary values: preserve negative signs and explicit credits, treat amounts as Canadian dollars unless the document specifies another currency, do not convert currencies, do not recompute printed totals, and flag apparent inconsistencies rather than correcting them silently.

Handwritten values may be corrections or final accepted amounts; prefer them over printed values only when the document clearly indicates they replace or amend the printed value.
"""


@dataclass(frozen=True)
class CashoutDocumentProcessingResult:
    # Never null: an unclassifiable document is UNKNOWN.
    classification: CashoutDocumentClassification
    # None when the caller supplied the classification (an assertion, not a
    # model score).
    classification_confidence: float | None
    # data/confidence/issues are None/empty when the classification has no
    # registered schema (UNKNOWN).
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
        *,
        classification: CashoutDocumentClassification | None = None,
    ) -> CashoutDocumentProcessingResult:
        if classification is not None:
            # A supplied classification (e.g. a user correcting the AI) is an
            # assertion, not a model score: the classify call is skipped and no
            # confidence is recorded.
            value = classification
            confidence = None
        else:
            classified = await self._documents.classify(
                document,
                CashoutDocumentClassification,
                instructions=_CLASSIFY_INSTRUCTIONS,
                hints=CASHOUT_CLASSIFICATION_HINTS,
            )
            # The generic layer expresses "can't classify" as a null value; the
            # domain folds it into the explicit UNKNOWN member.
            value = classified.value or CashoutDocumentClassification.UNKNOWN
            confidence = classified.confidence

        # UNKNOWN (and any type without a registered schema) has nothing to
        # extract — a supplied UNKNOWN therefore makes no AI call at all.
        schema = CASHOUT_DOCUMENT_SCHEMAS.get(value)
        if schema is None:
            return CashoutDocumentProcessingResult(
                classification=value,
                classification_confidence=confidence,
                data=None,
                confidence=None,
                issues=[],
                schema_name=None,
            )

        # TODO(document-ai): Add deterministic validation over the extracted
        # data (totals reconcile, amounts non-negative, ...).
        analysis = await self._documents.process(
            document, schema, instructions=_EXTRACT_INSTRUCTIONS
        )
        return CashoutDocumentProcessingResult(
            classification=value,
            classification_confidence=confidence,
            data=analysis.data,
            confidence=analysis.confidence,
            issues=analysis.issues,
            schema_name=schema.__name__,
        )


def build_cashout_document_processor(
    ai: AIClient, storage: DocumentStorageClient
) -> CashoutDocumentProcessor:
    """Compose a processor over the configured per-operation token budgets.

    Neither the processor nor its `DocumentAIClient` opens a resource — they
    only wrap the AI and storage clients, which own their own lifecycles — so
    each consumer calls this for itself rather than sharing one instance: the
    request dependency per request, the extraction outbox handler when the
    composition root constructs it.
    """
    return CashoutDocumentProcessor(
        DocumentAIClient(
            ai,
            storage,
            classification_max_tokens=settings.ai.CLASSIFICATION_MAX_TOKENS,
            extraction_max_tokens=settings.ai.EXTRACTION_MAX_TOKENS,
        )
    )


__all__ = [
    "CashoutDocumentProcessingResult",
    "CashoutDocumentProcessor",
    "build_cashout_document_processor",
]
