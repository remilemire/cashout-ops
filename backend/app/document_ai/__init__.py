# backend/app/document_ai/__init__.py

from __future__ import annotations

from .client import DocumentAIClient
from .cropping import (
    CropBounds,
    CroppedDocument,
    DocumentCropper,
    build_document_cropper,
)
from .errors import DocumentAIError, DocumentAIErrorCode, DocumentUnclassifiableError
from .fields import Money
from .hints import ClassificationHint, FieldHint
from .schemas import (
    DocumentAnalysis,
    DocumentClassification,
    DocumentClassificationResponse,
    FieldIssue,
)
from .types import DocumentRef

__all__ = [
    "ClassificationHint",
    "CropBounds",
    "CroppedDocument",
    "DocumentAIClient",
    "DocumentAIError",
    "DocumentAIErrorCode",
    "DocumentAnalysis",
    "DocumentClassification",
    "DocumentClassificationResponse",
    "DocumentCropper",
    "DocumentRef",
    "DocumentUnclassifiableError",
    "FieldHint",
    "FieldIssue",
    "Money",
    "build_document_cropper",
]
