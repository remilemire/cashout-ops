from __future__ import annotations

from app.core.config import settings
from app.core.providers import AIProvider
from app.document_ai import DocumentAIClient, DocumentRef
from app.document_cropping import DocumentCropper, build_document_cropper
from app.integrations.ai import AIClient
from app.integrations.ocr import TextDetector
from app.integrations.storage import DocumentNotFoundError, DocumentStorageClient
from app.lib.documents import DocumentContent

from .prompts import CLASSIFY_INSTRUCTIONS, EXTRACT_INSTRUCTIONS
from .registry import CASHOUT_CLASSIFICATION_HINTS, CASHOUT_DOCUMENT_SCHEMAS
from .types import (
    CashoutDocumentClassification,
    CashoutDocumentProcessingResult,
    StoredDocumentCrop,
)


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
        document_ai: DocumentAIClient,
        *,
        cropper: DocumentCropper,
        storage: DocumentStorageClient,
    ) -> None:
        self._document_ai = document_ai
        self._cropper = cropper
        self._storage = storage

    @property
    def provider(self) -> AIProvider:
        return self._document_ai.ai.provider

    @property
    def model(self) -> str:
        return self._document_ai.ai.model

    async def crop(self, upload: DocumentRef) -> list[StoredDocumentCrop]:
        """Find the documents printed in the stored upload and store a crop of
        each beside it, in reading order.

        Empty when there is nothing to crop to — no detectable text, cropping
        switched off — and the upload should be read whole. A missing
        original is empty too: `process` reports that as MISSING_DOCUMENT,
        where the caller already handles it.
        """
        try:
            data = await self._storage.read(upload.storage_key)
        except DocumentNotFoundError:
            return []
        crops = await self._cropper.crop(
            DocumentContent(data=data, content_type=upload.content_type)
        )
        stored: list[StoredDocumentCrop] = []
        for number, crop in enumerate(crops, start=1):
            # Sibling objects, not child paths: under local storage the
            # original's key is a file, so nothing can nest beneath it.
            storage_key = f"{upload.storage_key}-crop-{number}"
            await self._storage.write(storage_key, crop.content.data)
            stored.append(
                StoredDocumentCrop(
                    ref=DocumentRef(
                        storage_key=storage_key,
                        content_type=crop.content.content_type,
                    ),
                    bounds=crop.bounds,
                )
            )
        return stored

    async def process(
        self,
        source: DocumentRef,
        *,
        classification: CashoutDocumentClassification | None = None,
    ) -> CashoutDocumentProcessingResult:
        """Classify the document at `source` and extract its type's schema.

        `source` is whatever the caller wants read: a crop `crop` stored, or
        the upload itself when there was none.

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
            classified = await self._document_ai.classify(
                source,
                CashoutDocumentClassification,
                instructions=CLASSIFY_INSTRUCTIONS,
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
        analysis = await self._document_ai.process(
            source, schema, instructions=EXTRACT_INSTRUCTIONS
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
    """Build a processor with the configured token budgets and crop settings.

    The supplied AI, storage, and detector clients retain their own lifecycles.
    A None detector disables cropping.
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


__all__ = ["CashoutDocumentProcessor", "build_cashout_document_processor"]
