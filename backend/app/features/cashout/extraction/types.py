from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.document_ai import DocumentRef, FieldIssue
from app.document_cropping import CropBounds

from .schemas import CashoutDocumentSchema


# The document types the AI can classify a cashout document as. There is no
# "none of the above" member: a document the model cannot place is a failed
# extraction (DocumentUnclassifiableError), not a classification — so every
# classification here has a registered extraction schema.
class CashoutDocumentClassification(StrEnum):
    TOUCHBISTRO_REPORT = "touchbistro_report"
    SERVER_SUMMARY_REPORT = "server_summary_report"


@dataclass(frozen=True)
class StoredDocumentCrop:
    """One document found in an upload, cropped out and stored beside it.

    `ref` is what extraction reads in place of the whole upload (and what
    the cashier previews); `bounds` is where in the upload it was cut from
    — the `DocumentCrop` the cropper produced, with its bytes written to
    storage and only their key kept.
    """

    ref: DocumentRef
    bounds: CropBounds


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


__all__ = [
    "CashoutDocumentClassification",
    "CashoutDocumentProcessingResult",
    "StoredDocumentCrop",
]
