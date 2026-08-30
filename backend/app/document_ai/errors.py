# backend/app/document_ai/errors.py

from __future__ import annotations

from enum import StrEnum
from typing import Mapping

from app.integrations.ai import AIAnalysisError, AIErrorCode


# The document-analysis failure modes callers may persist. Most re-specialize
# a provider-neutral AIErrorCode into document vocabulary (the mapping below);
# UNCLASSIFIABLE_DOCUMENT is this layer's own — the AI call itself succeeded
# and placed the document as none of the allowed types.
class DocumentAIErrorCode(StrEnum):
    SERVICE_UNAVAILABLE = "service_unavailable"
    DOCUMENT_REJECTED = "document_rejected"
    UNREADABLE_DOCUMENT = "unreadable_document"
    OUTPUT_LIMIT_REACHED = "output_limit_reached"
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    UNCLASSIFIABLE_DOCUMENT = "unclassifiable_document"


# Exhaustive over AIErrorCode (unit-test-enforced): every AI failure the
# client re-raises lands under a document code.
AI_ERROR_CODES: Mapping[AIErrorCode, DocumentAIErrorCode] = {
    AIErrorCode.SERVICE_UNAVAILABLE: DocumentAIErrorCode.SERVICE_UNAVAILABLE,
    AIErrorCode.CONTENT_REFUSED: DocumentAIErrorCode.DOCUMENT_REJECTED,
    AIErrorCode.INVALID_RESPONSE: DocumentAIErrorCode.UNREADABLE_DOCUMENT,
    AIErrorCode.OUTPUT_LIMIT_REACHED: DocumentAIErrorCode.OUTPUT_LIMIT_REACHED,
    AIErrorCode.UNSUPPORTED_CONTENT_TYPE: DocumentAIErrorCode.UNSUPPORTED_FILE_TYPE,
}


class DocumentAIError(Exception):
    """A document analysis failed in a way callers may persist.

    Carries its own code and message so catchers translate from these alone,
    never by inspecting `__cause__` (the chained AIAnalysisError, when there
    is one, is kept for tracebacks only).
    """

    def __init__(self, code: DocumentAIErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    @classmethod
    def from_ai_error(cls, error: AIAnalysisError) -> DocumentAIError:
        return cls(AI_ERROR_CODES[error.code], error.message)


class DocumentUnclassifiableError(DocumentAIError):
    """The model placed the document as none of the allowed types."""

    def __init__(self, message: str):
        super().__init__(DocumentAIErrorCode.UNCLASSIFIABLE_DOCUMENT, message)


__all__ = [
    "AI_ERROR_CODES",
    "DocumentAIError",
    "DocumentAIErrorCode",
    "DocumentUnclassifiableError",
]
