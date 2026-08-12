# backend/tests/unit/test_extraction.py

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.core.ai import AIProvider
from app.document_ai import (
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
    compose_instructions,
)
from app.lib.documents import DocumentContentType
from tests.support.fakes import FakeAIClient, FakeDocumentStorage

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
    processor = CashoutDocumentProcessor(
        DocumentAIClient(
            ai, storage, classification_max_tokens=512, extraction_max_tokens=2048
        )
    )
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

    assert result.classification is CashoutDocumentClassification.MANUAL_NOTE
    assert result.classification_confidence == 0.9
    assert isinstance(result.data, ManualNoteData)
    assert result.data.note == "cash short $5"
    assert result.confidence == 0.8
    assert result.issues[0].path == "note"
    assert result.schema_name == "ManualNoteData"


@pytest.mark.parametrize(
    "value",
    [None, CashoutDocumentClassification.UNKNOWN],
    ids=["null-folded-to-unknown", "unknown-picked-directly"],
)
async def test_processor_unknown_returns_no_data(
    value: CashoutDocumentClassification | None,
) -> None:
    processor, ref = await _build_processor(
        classification=_classification(value, confidence=0.2),
    )

    result = await processor.process(ref)

    assert result.classification is CashoutDocumentClassification.UNKNOWN
    assert result.classification_confidence == 0.2
    assert result.data is None
    assert result.confidence is None
    assert result.issues == []
    assert result.schema_name is None


async def test_processor_propagates_ai_error() -> None:
    processor, ref = await _build_processor(
        error=AIAnalysisError(AIErrorCode.SERVICE_UNAVAILABLE, "provider down"),
    )

    with pytest.raises(AIAnalysisError) as exc_info:
        await processor.process(ref)
    assert exc_info.value.code is AIErrorCode.SERVICE_UNAVAILABLE


async def test_processor_layers_domain_instructions_on_both_calls() -> None:
    storage = FakeDocumentStorage()
    await storage.write("doc-key", b"file-bytes")
    ai = FakeAIClient(
        classification=_classification(CashoutDocumentClassification.MANUAL_NOTE),
        extraction=DocumentAnalysis[ManualNoteData](
            data=ManualNoteData(note="cash short $5"), confidence=0.8
        ),
    )
    processor = CashoutDocumentProcessor(
        DocumentAIClient(
            ai, storage, classification_max_tokens=111, extraction_max_tokens=222
        )
    )

    await processor.process(
        DocumentRef(storage_key="doc-key", content_type=DocumentContentType.PDF)
    )

    # compose_instructions appends the caller's extra under this header, so its
    # presence proves the domain instructions were layered onto the base ones.
    classify_call, extract_call = ai.calls
    (_, _, classify_instructions, classify_max_tokens) = classify_call
    (_, _, extract_instructions, extract_max_tokens) = extract_call
    assert classify_instructions is not None
    assert "# Additional instructions" in classify_instructions
    assert "TOUCHBISTRO_SERVER_SHIFT_REPORT" in classify_instructions
    assert extract_instructions is not None
    assert "# Additional instructions" in extract_instructions

    # Each operation runs under its own output-token budget.
    assert classify_max_tokens == 111
    assert extract_max_tokens == 222


def test_processor_exposes_provider_and_model() -> None:
    ai = FakeAIClient(model="fake-model")
    processor = CashoutDocumentProcessor(
        DocumentAIClient(
            ai,
            FakeDocumentStorage(),
            classification_max_tokens=512,
            extraction_max_tokens=2048,
        )
    )

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
