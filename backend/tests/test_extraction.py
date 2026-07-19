# backend/tests/test_extraction.py

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.documents import (
    DocumentAIClient,
    DocumentAnalysis,
    DocumentClassification,
    DocumentRef,
    FieldIssue,
)
from app.features.cashout.extraction import CashoutDocumentProcessor
from app.features.cashout.extraction.schemas import ManualNoteData
from app.features.cashout.types import CashoutDocumentClassification
from app.integrations.ai import (
    AIAnalysisError,
    AIErrorCode,
    AIProvider,
    compose_instructions,
)
from app.lib.documents import DocumentContentType

from .fakes import FakeAIClient, FakeDocumentStorage

# ================================
# ---------- Processor -----------
# ================================


def _classification(
    value: CashoutDocumentClassification | None, confidence: float = 0.9
) -> DocumentClassification[CashoutDocumentClassification]:
    return DocumentClassification[CashoutDocumentClassification](
        value=value, confidence=confidence
    )


async def _build_processor(
    *,
    classification: BaseModel | None = None,
    extraction: BaseModel | None = None,
    error: AIAnalysisError | None = None,
) -> tuple[CashoutDocumentProcessor, DocumentRef]:
    storage = FakeDocumentStorage()
    await storage.write("doc-key", b"file-bytes")
    ai = FakeAIClient(classification=classification, extraction=extraction, error=error)
    processor = CashoutDocumentProcessor(DocumentAIClient(ai, storage))
    ref = DocumentRef(storage_key="doc-key", content_type=DocumentContentType.PDF)
    return processor, ref


async def test_processor_classifies_and_extracts() -> None:
    processor, ref = await _build_processor(
        classification=_classification(CashoutDocumentClassification.MANUAL_NOTE),
        extraction=DocumentAnalysis[ManualNoteData](
            data=ManualNoteData(note="cash short $5"),
            confidence=0.8,
            issues=[FieldIssue(path="note", message="handwriting was unclear")],
        ),
    )

    result = await processor.process(ref)

    assert result.classification.value is CashoutDocumentClassification.MANUAL_NOTE
    assert result.classification.confidence == 0.9
    assert isinstance(result.data, ManualNoteData)
    assert result.data.note == "cash short $5"
    assert result.confidence == 0.8
    assert result.issues[0].path == "note"
    assert result.schema_name == "ManualNoteData"


async def test_processor_unclassified_returns_no_data() -> None:
    processor, ref = await _build_processor(
        classification=_classification(None, confidence=0.2),
    )

    result = await processor.process(ref)

    assert result.classification.value is None
    assert result.data is None
    assert result.confidence is None
    assert result.issues == []
    assert result.schema_name is None


async def test_processor_propagates_ai_error() -> None:
    processor, ref = await _build_processor(
        error=AIAnalysisError(AIErrorCode.PROVIDER_ERROR, "provider down"),
    )

    with pytest.raises(AIAnalysisError) as exc_info:
        await processor.process(ref)
    assert exc_info.value.code is AIErrorCode.PROVIDER_ERROR


def test_processor_exposes_provider_and_model() -> None:
    ai = FakeAIClient(model="fake-model")
    processor = CashoutDocumentProcessor(DocumentAIClient(ai, FakeDocumentStorage()))

    assert processor.provider is AIProvider.ANTHROPIC
    assert processor.model == "fake-model"


# ================================
# --------- Instructions ---------
# ================================


def test_compose_instructions_without_extra_returns_base() -> None:
    assert compose_instructions("BASE") == "BASE"


def test_compose_instructions_appends_extra_under_header() -> None:
    composed = compose_instructions("BASE", "EXTRA")

    assert composed.startswith("BASE")
    assert "EXTRA" in composed
    assert "# Additional instructions" in composed
