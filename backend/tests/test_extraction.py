# backend/tests/test_extraction.py

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest
from anthropic import APIError
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
from app.features.cashout.types import CashoutDocumentType
from app.integrations.ai import (
    AIAnalysisError,
    AIErrorCode,
    AIProvider,
    compose_instructions,
)
from app.integrations.ai.anthropic import AnthropicAIClient, _to_document_block
from app.lib.documents import DocumentContent, DocumentContentType

from .fakes import FakeAIClient, FakeDocumentStorage

# ================================
# ---------- Processor -----------
# ================================


def _classification(
    value: CashoutDocumentType, confidence: float = 0.9
) -> DocumentClassification[CashoutDocumentType]:
    return DocumentClassification[CashoutDocumentType](
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
        classification=_classification(CashoutDocumentType.MANUAL_NOTE),
        extraction=DocumentAnalysis[ManualNoteData](
            data=ManualNoteData(note="cash short $5"),
            confidence=0.8,
            issues=[FieldIssue(path="note", message="handwriting was unclear")],
        ),
    )

    result = await processor.process(ref)

    assert result.classification.value is CashoutDocumentType.MANUAL_NOTE
    assert result.classification.confidence == 0.9
    assert isinstance(result.data, ManualNoteData)
    assert result.data.note == "cash short $5"
    assert result.confidence == 0.8
    assert result.issues[0].path == "note"
    assert result.schema_name == "ManualNoteData"


async def test_processor_unknown_classification_returns_no_data() -> None:
    processor, ref = await _build_processor(
        classification=_classification(CashoutDocumentType.UNKNOWN, confidence=0.2),
    )

    result = await processor.process(ref)

    assert result.classification.value is CashoutDocumentType.UNKNOWN
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
# ------ AnthropicAIClient -------
# ================================


@dataclass
class _FakeParsed:
    stop_reason: str
    parsed_output: BaseModel | None


class _FakeMessages:
    def __init__(
        self, *, response: _FakeParsed | None = None, exc: Exception | None = None
    ) -> None:
        self._response = response
        self._exc = exc
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> _FakeParsed:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response


class _FakeAnthropic:
    def __init__(
        self, *, response: _FakeParsed | None = None, exc: Exception | None = None
    ) -> None:
        self.messages = _FakeMessages(response=response, exc=exc)


def _anthropic_client(**kwargs: object) -> AnthropicAIClient:
    fake = _FakeAnthropic(**kwargs)  # type: ignore[arg-type]
    return AnthropicAIClient(fake, model="claude-test")  # type: ignore[arg-type]


async def test_anthropic_client_returns_parsed_output() -> None:
    note = ManualNoteData(note="ok")
    client = _anthropic_client(response=_FakeParsed("end_turn", note))

    result = await client.analyze(
        DocumentContent(data=b"pdf", content_type=DocumentContentType.PDF),
        ManualNoteData,
    )

    assert result is note


async def test_anthropic_client_raises_on_refusal() -> None:
    client = _anthropic_client(response=_FakeParsed("refusal", None))

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze(
            DocumentContent(data=b"pdf", content_type=DocumentContentType.PDF),
            ManualNoteData,
        )
    assert exc_info.value.code is AIErrorCode.REFUSED


async def test_anthropic_client_raises_when_no_parsed_output() -> None:
    client = _anthropic_client(response=_FakeParsed("end_turn", None))

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("some text", ManualNoteData)
    assert exc_info.value.code is AIErrorCode.INVALID_RESPONSE


async def test_anthropic_client_wraps_provider_errors() -> None:
    api_error = APIError(
        "boom", request=httpx.Request("POST", "http://test"), body=None
    )
    client = _anthropic_client(exc=api_error)

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData)
    assert exc_info.value.code is AIErrorCode.PROVIDER_ERROR


def test_to_document_block_maps_pdf() -> None:
    block = _to_document_block(
        DocumentContent(data=b"pdf-bytes", content_type=DocumentContentType.PDF)
    )

    assert block["type"] == "document"
    assert block["source"]["media_type"] == "application/pdf"


def test_to_document_block_maps_image() -> None:
    block = _to_document_block(
        DocumentContent(data=b"png-bytes", content_type=DocumentContentType.PNG)
    )

    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/png"


async def test_anthropic_client_always_sends_base_instructions() -> None:
    fake = _FakeAnthropic(response=_FakeParsed("end_turn", ManualNoteData(note="ok")))
    client = AnthropicAIClient(fake, model="claude-test")  # type: ignore[arg-type]

    await client.analyze("text", ManualNoteData, instructions="EXTRA CONTEXT")

    system = fake.messages.calls[0]["system"]
    assert isinstance(system, str)
    assert "document-analysis assistant" in system  # base persona always present
    assert "EXTRA CONTEXT" in system  # caller instructions appended


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
