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
from app.document_cropping import CropBounds, DocumentCropper, build_document_cropper
from app.integrations.ai import AIClient
from app.integrations.ocr import TextDetector
from app.integrations.storage import DocumentNotFoundError, DocumentStorageClient
from app.lib.documents import DocumentContent, DocumentContentType

from .registry import CASHOUT_CLASSIFICATION_HINTS, CASHOUT_DOCUMENT_SCHEMAS
from .schemas import CashoutDocumentSchema
from .types import CashoutDocumentClassification

# Per-type signals live in CASHOUT_CLASSIFICATION_HINTS; this keeps only the
# framing, the cross-type distinctions, and the "none of the above" guidance
# (markers can't describe the absence of a type).
_CLASSIFY_INSTRUCTIONS = """
The document is one end-of-shift record from a restaurant cashout.

Leave the classification unset for anything else, including unrelated photos and documents too degraded to identify.

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
class DocumentCrop:
    """One document found in a stored upload, cropped out and written beside
    the original.

    What extraction reads in place of the whole upload, and what the cashier
    previews: the printed area text detection found, in the original's format
    (PNG for a PDF's rendered page), with where it sits in the upright
    original — and on which page, for a PDF.
    """

    storage_key: str
    content_type: DocumentContentType
    bounds: CropBounds
    page: int | None

    def bounds_json(self) -> dict[str, int]:
        bounds = self.bounds.as_json()
        if self.page is not None:
            bounds["page"] = self.page
        return bounds


@dataclass(frozen=True)
class CashoutDocumentProcessingResult:
    """A placed document and what was extracted from it.

    Only produced for a document that was classified: an unclassifiable one
    raises DocumentUnclassifiableError instead (from the document_ai layer),
    so every classification here has a schema and extracted data behind it.
    """

    classification: CashoutDocumentClassification
    # None when the caller supplied the classification (an assertion, not a
    # model score).
    classification_confidence: float | None
    data: CashoutDocumentSchema
    confidence: float
    issues: list[FieldIssue]
    schema_name: str
    # The SCHEMA_VERSION the data was extracted under: which shape of the
    # named schema the dumped payload follows when read back later.
    schema_version: int


class CashoutDocumentProcessor:
    """Maps generic document analysis onto the cashout domain.

    Coordinates the two generic components an extraction needs — the
    cropper, which finds the documents printed in an upload and cuts each
    out, and the document AI, which classifies and extracts one document —
    without either knowing of the other. The caller sequences them (`crop`,
    then `process` over each crop) and persists what each reports.
    """

    def __init__(
        self,
        documents: DocumentAIClient,
        *,
        cropper: DocumentCropper,
        storage: DocumentStorageClient,
    ) -> None:
        self._documents = documents
        self._cropper = cropper
        self._storage = storage

    @property
    def provider(self) -> AIProvider:
        return self._documents.ai.provider

    @property
    def model(self) -> str:
        return self._documents.ai.model

    async def crop(self, document: DocumentRef) -> list[DocumentCrop]:
        """Find the documents printed in the stored upload and store a crop of
        each beside it, in reading order.

        Empty when there is nothing to crop to — no detectable text, cropping
        switched off — and the upload should be read whole. A missing
        original is empty too: `process` reports that as MISSING_DOCUMENT,
        where the caller already handles it.
        """
        try:
            data = await self._storage.read(document.storage_key)
        except DocumentNotFoundError:
            return []
        cropped = await self._cropper.crop(
            DocumentContent(data=data, content_type=document.content_type)
        )
        crops: list[DocumentCrop] = []
        for number, crop in enumerate(cropped, start=1):
            # Sibling objects, not child paths: under local storage the
            # original's key is a file, so nothing can nest beneath it.
            storage_key = f"{document.storage_key}-crop-{number}"
            await self._storage.write(storage_key, crop.data)
            crops.append(
                DocumentCrop(
                    storage_key=storage_key,
                    content_type=crop.content_type,
                    bounds=crop.bounds,
                    page=crop.page,
                )
            )
        return crops

    async def process(
        self,
        document: DocumentRef,
        *,
        classification: CashoutDocumentClassification | None = None,
    ) -> CashoutDocumentProcessingResult:
        """Classify the document and extract its type's schema from it.

        `document` is whatever the caller wants read: the crop `crop`
        produced, or the original when there was none.

        Raises DocumentAIError — DocumentUnclassifiableError when the model
        places the document as none of the known types, or a re-raised AI
        failure; the caller persists either as a failed analysis.
        """
        if classification is not None:
            # A supplied classification (e.g. a user correcting the AI) is an
            # assertion, not a model score: the classify call is skipped and no
            # confidence is recorded.
            value = classification
            confidence = None
        else:
            # An unclassifiable document raises out of classify — a failed
            # extraction, never a classification of its own.
            classified = await self._documents.classify(
                document,
                CashoutDocumentClassification,
                instructions=_CLASSIFY_INSTRUCTIONS,
                hints=CASHOUT_CLASSIFICATION_HINTS,
            )
            value = classified.value
            confidence = classified.confidence

        # Total by construction: every classification has a registered schema
        # (registry-level unit test).
        schema = CASHOUT_DOCUMENT_SCHEMAS[value]

        # No validation pass here: the schema enforces per-field validity
        # (Money parsing, non-negative counts), and cross-document checks
        # belong to data/reconciliation.py when the submission completes.
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
            schema_version=schema.SCHEMA_VERSION,
        )


def build_cashout_document_processor(
    ai: AIClient, storage: DocumentStorageClient, text_detector: TextDetector | None
) -> CashoutDocumentProcessor:
    """Compose a processor over the configured token budgets and OCR settings.

    Neither the processor nor its `DocumentAIClient` and `DocumentCropper`
    opens a resource — they only wrap the AI, storage, and detector clients,
    which own their own lifecycles — so each consumer calls this for itself
    rather than sharing one instance: the request dependency per request,
    the extraction outbox handler when the composition root constructs it.
    A None detector (cropping disabled) makes a processor that never crops.
    """
    return CashoutDocumentProcessor(
        DocumentAIClient(
            ai,
            storage,
            classification_max_tokens=settings.ai.CLASSIFICATION_MAX_TOKENS,
            extraction_max_tokens=settings.ai.EXTRACTION_MAX_TOKENS,
        ),
        cropper=build_document_cropper(text_detector),
        storage=storage,
    )


__all__ = [
    "CashoutDocumentProcessingResult",
    "CashoutDocumentProcessor",
    "DocumentCrop",
    "build_cashout_document_processor",
]
