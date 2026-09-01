# backend/app/document_ai/client.py

from __future__ import annotations

from collections.abc import Mapping

from app.integrations.ai import (
    AIAnalysisError,
    AIClient,
    AIContent,
    ResponseModelT,
    compose_instructions,
)
from app.integrations.storage import DocumentNotFoundError, DocumentStorageClient
from app.lib.documents import DocumentContent

from .errors import DocumentAIError, DocumentAIErrorCode, DocumentUnclassifiableError
from .hints import (
    ClassificationHint,
    collect_field_hints,
    render_classification_hints,
    render_field_hints,
)
from .schemas import (
    ClassificationT,
    DocumentAnalysis,
    DocumentClassification,
    DocumentClassificationResponse,
)
from .types import DocumentRef

# Base instructions are always present; a caller's `instructions` are appended
# on top (see compose_instructions), never used as a replacement.
_CLASSIFY_INSTRUCTIONS = """
Classify the supplied document using only the document types allowed by the response schema.

* Base the classification on the whole document — title, issuer, layout, field labels, table structure, apparent purpose — not on a single keyword, the filename, or a caller-provided label.
* If the document does not clearly match an allowed type, leave the classification null rather than forcing the most likely option.
* Reduce confidence when the document is partial, blurry, cropped, mixed with another document, or missing identifying headings.
"""

_EXTRACT_INSTRUCTIONS = """Extract the requested structured data from the supplied document.

* Base each value on visible evidence, preserving its sign, decimal value, date, identifier, and unit. Do not calculate, reconcile, normalize, or reinterpret values unless explicitly requested.
* Prefer a clearly labelled value over an inferred one. When multiple plausible values exist, use the one most directly associated with the requested field and report the ambiguity through the schema’s warning or confidence fields; never choose silently.
* Use null when a field is absent, illegible, or cannot be identified reliably. Do not copy unrelated document text into free-form fields.
"""


def _join_sections(*sections: str | None) -> str | None:
    """Collapse the present sections into the one `extra` compose_instructions takes.

    Returning None when nothing is present preserves the exact hint-less,
    instruction-less behavior: no "# Additional instructions" header at all.
    """
    present = [section for section in sections if section is not None]
    if not present:
        return None
    return "\n\n".join(present)


class DocumentAIClient:
    """Generic classification and structured extraction for stored documents.

    Each operation has its own output-token budget: a classification is a tiny
    fixed-shape object, while an extraction scales with the schema.

    Both operations raise DocumentAIError: AI-layer failures are re-raised
    under this layer's document vocabulary, a stored document whose bytes are
    gone raises MISSING_DOCUMENT, and a classification the model resolves to
    none of the allowed types raises DocumentUnclassifiableError.
    """

    def __init__(
        self,
        ai: AIClient,
        storage: DocumentStorageClient,
        *,
        classification_max_tokens: int,
        extraction_max_tokens: int,
    ) -> None:
        self.ai = ai
        self._storage = storage
        self._classification_max_tokens = classification_max_tokens
        self._extraction_max_tokens = extraction_max_tokens

    async def classify(
        self,
        document: DocumentRef,
        classification_type: type[ClassificationT],
        *,
        instructions: str | None = None,
        hints: Mapping[ClassificationT, ClassificationHint] | None = None,
    ) -> DocumentClassification[ClassificationT]:
        # Sharing `ClassificationT` with `classification_type` is the key
        # validation: hints for a different enum fail to type-check.
        extra = _join_sections(
            instructions,
            render_classification_hints(hints) if hints is not None else None,
        )
        response = await self._analyze(
            await self._read(document),
            DocumentClassificationResponse[classification_type],
            instructions=compose_instructions(_CLASSIFY_INSTRUCTIONS, extra),
            max_tokens=self._classification_max_tokens,
        )
        if response.value is None:
            raise DocumentUnclassifiableError(
                "The document matches none of the allowed document types."
            )
        return DocumentClassification[classification_type](
            value=response.value, confidence=response.confidence
        )

    async def process(
        self,
        document: DocumentRef,
        response_model: type[ResponseModelT],
        *,
        instructions: str | None = None,
    ) -> DocumentAnalysis[ResponseModelT]:
        # Field hints ride the response model's `Annotated` metadata rather
        # than being passed in, so every caller extracting a schema gets its
        # declared hints.
        extra = _join_sections(
            instructions, render_field_hints(collect_field_hints(response_model))
        )
        return await self._analyze(
            await self._read(document),
            DocumentAnalysis[response_model],
            instructions=compose_instructions(_EXTRACT_INSTRUCTIONS, extra),
            max_tokens=self._extraction_max_tokens,
        )

    async def _analyze(
        self,
        content: AIContent,
        response_model: type[ResponseModelT],
        *,
        instructions: str | None,
        max_tokens: int,
    ) -> ResponseModelT:
        try:
            return await self.ai.analyze(
                content,
                response_model,
                instructions=instructions,
                max_tokens=max_tokens,
            )
        except AIAnalysisError as exc:
            # Chained for the traceback only: the raised error carries the
            # mapped code and message itself.
            raise DocumentAIError.from_ai_error(exc) from exc

    async def _read(self, document: DocumentRef) -> DocumentContent:
        try:
            data = await self._storage.read(document.storage_key)
        except DocumentNotFoundError as exc:
            # The referenced bytes are gone (lost or deleted out of band):
            # re-raised under this layer's vocabulary so callers persist it
            # like any other document failure instead of crashing.
            raise DocumentAIError(
                DocumentAIErrorCode.MISSING_DOCUMENT, str(exc)
            ) from exc
        return DocumentContent(data=data, content_type=document.content_type)


__all__ = ["DocumentAIClient"]
