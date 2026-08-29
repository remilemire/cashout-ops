# backend/tests/unit/test_extraction.py

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.providers import AIProvider
from app.document_ai import (
    ClassificationHint,
    DocumentAIClient,
    DocumentAnalysis,
    DocumentClassification,
    DocumentRef,
    FieldHint,
    FieldIssue,
    Money,
)
from app.document_ai.hints import collect_field_hints
from app.features.cashout.extraction import CashoutDocumentProcessor
from app.features.cashout.extraction.registry import (
    CASHOUT_CLASSIFICATION_HINTS,
    CASHOUT_DOCUMENT_SCHEMAS,
)
from app.features.cashout.extraction.schemas import (
    ServerSummaryReportData,
    TouchBistroReportData,
)
from app.features.cashout.extraction.types import CashoutDocumentClassification
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
        classification=_classification(
            CashoutDocumentClassification.SERVER_SUMMARY_REPORT
        ),
        extraction=DocumentAnalysis[ServerSummaryReportData](
            data=ServerSummaryReportData(
                grand_total=Decimal("1234.56"), grand_total_transaction_count=42
            ),
            confidence=0.8,
            issues=[FieldIssue(path="grand_total", message="the print was faint")],
        ),
    )

    result = await processor.process(ref)

    assert result.classification is CashoutDocumentClassification.SERVER_SUMMARY_REPORT
    assert result.classification_confidence == 0.9
    assert isinstance(result.data, ServerSummaryReportData)
    assert result.data.grand_total == Decimal("1234.56")
    assert result.data.grand_total_transaction_count == 42
    assert result.confidence == 0.8
    assert result.issues[0].path == "grand_total"
    assert result.schema_name == "ServerSummaryReportData"


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
        classification=_classification(
            CashoutDocumentClassification.SERVER_SUMMARY_REPORT
        ),
        extraction=DocumentAnalysis[ServerSummaryReportData](
            data=ServerSummaryReportData(
                grand_total=Decimal("1234.56"), grand_total_transaction_count=42
            ),
            confidence=0.8,
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
    # Classification hints render keyed by enum value with their markers.
    assert "touchbistro_report" in classify_instructions
    assert "Created on an iPad using TouchBistro Pro near the bottom" in (
        classify_instructions
    )
    assert extract_instructions is not None
    assert "# Additional instructions" in extract_instructions
    # Field hints harvested from the schema render per-field guidance.
    assert "* grand_total — " in extract_instructions
    assert "beside Grand Total" in extract_instructions

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
# -------- Hint rendering --------
# ================================

# Domain-agnostic fixtures: rendering behavior belongs to document_ai, not to
# the cashout declarations.


class _ShelterDocument(StrEnum):
    ADOPTION_FORM = "adoption_form"
    VACCINE_RECORD = "vaccine_record"


_SHELTER_HINTS: Mapping[_ShelterDocument, ClassificationHint] = {
    _ShelterDocument.ADOPTION_FORM: ClassificationHint(
        markers=("a household questionnaire", "an adopter signature line"),
        anti_markers=("a table of injection dates",),
    ),
    # No anti_markers: the rendered bullet must skip the group entirely.
    _ShelterDocument.VACCINE_RECORD: ClassificationHint(
        markers=("a table of injection dates",),
    ),
}


class _ShelterIntakeRecord(BaseModel):
    owner_name: Annotated[
        str | None,
        FieldHint(
            labels=("Owner", "Guardian"),
            sections=("intake",),
            anchors=("printed beside the signature line",),
            anti_anchors=("Veterinarian",),
        ),
    ] = None
    # Deliberately unannotated: must produce no bullet.
    kennel_number: str | None = None


class _BareRecord(BaseModel):
    name: str | None = None


class _EmptyHintRecord(BaseModel):
    name: Annotated[str | None, FieldHint()] = None


async def _build_document_client(
    *,
    classification: BaseModel | None = None,
    extraction: BaseModel | None = None,
) -> tuple[DocumentAIClient, FakeAIClient, DocumentRef]:
    storage = FakeDocumentStorage()
    await storage.write("doc-key", b"file-bytes")
    ai = FakeAIClient(classification=classification, extraction=extraction)
    client = DocumentAIClient(
        ai, storage, classification_max_tokens=512, extraction_max_tokens=2048
    )
    ref = DocumentRef(storage_key="doc-key", content_type=DocumentContentType.PDF)
    return client, ai, ref


def _only_instructions(ai: FakeAIClient) -> str:
    (call,) = ai.calls
    (_, _, instructions, _) = call
    assert instructions is not None
    return instructions


def _shelter_classification() -> DocumentClassification[_ShelterDocument]:
    return DocumentClassification[_ShelterDocument](
        value=_ShelterDocument.ADOPTION_FORM, confidence=0.9
    )


def _shelter_extraction() -> DocumentAnalysis[_ShelterIntakeRecord]:
    return DocumentAnalysis[_ShelterIntakeRecord](
        data=_ShelterIntakeRecord(), confidence=0.5
    )


async def test_classify_renders_hints_by_value_after_caller_instructions() -> None:
    client, ai, ref = await _build_document_client(
        classification=_shelter_classification()
    )

    await client.classify(
        ref,
        _ShelterDocument,
        instructions="Prefer the most recent stamp.",
        hints=_SHELTER_HINTS,
    )

    instructions = _only_instructions(ai)
    assert instructions.count("# Additional instructions") == 1
    # Caller instructions come first; hints follow inside the same section.
    assert instructions.index("Prefer the most recent stamp.") < instructions.index(
        "* adoption_form"
    )
    assert (
        "* adoption_form — expect: a household questionnaire, an adopter"
        " signature line; unlikely if: a table of injection dates." in instructions
    )
    # The last bullet ends the prompt, and its empty group is skipped rather
    # than rendered empty.
    assert instructions.rstrip().endswith(
        "* vaccine_record — expect: a table of injection dates."
    )


async def test_rendered_hints_use_no_structural_vocabulary() -> None:
    client, ai, ref = await _build_document_client(
        classification=_shelter_classification(),
        extraction=_shelter_extraction(),
    )

    await client.classify(ref, _ShelterDocument, hints=_SHELTER_HINTS)
    await client.process(ref, _ShelterIntakeRecord)

    for _, _, instructions, _ in ai.calls:
        assert instructions is not None
        # The base prompts legitimately say e.g. "field labels"; the
        # natural-language directive applies to the rendered hints, which are
        # everything after the header here (no caller instructions).
        rendered = instructions.split("# Additional instructions", 1)[1].lower()
        for term in (
            "markers",
            "anti-markers",
            "labels",
            "sections",
            "anchors",
            "anti-anchors",
        ):
            assert term not in rendered


_NO_HINTS: Mapping[_ShelterDocument, ClassificationHint] = {}


@pytest.mark.parametrize("hints", [None, _NO_HINTS], ids=["none", "empty"])
async def test_classify_without_hint_content_adds_nothing(
    hints: Mapping[_ShelterDocument, ClassificationHint] | None,
) -> None:
    client, ai, ref = await _build_document_client(
        classification=_shelter_classification()
    )

    await client.classify(
        ref, _ShelterDocument, instructions="CALLER EXTRA", hints=hints
    )

    instructions = _only_instructions(ai)
    assert "# Additional instructions" in instructions
    # Nothing renders after the caller's own instructions.
    assert instructions.rstrip().endswith("CALLER EXTRA")


async def test_classify_without_instructions_or_hints_omits_extra_header() -> None:
    client, ai, ref = await _build_document_client(
        classification=_shelter_classification()
    )

    await client.classify(ref, _ShelterDocument)

    assert "# Additional instructions" not in _only_instructions(ai)


async def test_process_renders_annotated_field_hints() -> None:
    client, ai, ref = await _build_document_client(extraction=_shelter_extraction())

    await client.process(ref, _ShelterIntakeRecord, instructions="CALLER EXTRA")

    instructions = _only_instructions(ai)
    assert instructions.count("# Additional instructions") == 1
    assert instructions.index("CALLER EXTRA") < instructions.index("* owner_name")
    assert (
        '* owner_name — usually labelled "Owner" or "Guardian"; found in the'
        " intake section; look near: printed beside the signature line; do not"
        ' confuse with values marked "Veterinarian".' in instructions
    )
    assert "kennel_number" not in instructions


async def test_process_without_hints_or_instructions_omits_extra_header() -> None:
    client, ai, ref = await _build_document_client(
        extraction=DocumentAnalysis[_BareRecord](data=_BareRecord(), confidence=0.5)
    )

    await client.process(ref, _BareRecord)

    assert "# Additional instructions" not in _only_instructions(ai)


async def test_field_hint_with_all_groups_empty_renders_nothing() -> None:
    client, ai, ref = await _build_document_client(
        extraction=DocumentAnalysis[_EmptyHintRecord](
            data=_EmptyHintRecord(), confidence=0.5
        )
    )

    await client.process(ref, _EmptyHintRecord)

    assert "# Additional instructions" not in _only_instructions(ai)


# ================================
# ---------- Field types ---------
# ================================


class _Amounts(BaseModel):
    """Provider output reaches a schema through `model_validate`, never a typed
    constructor, so the string cases below go in the same way."""

    model_config = ConfigDict(extra="forbid")

    total: Money


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("1234.56", "1234.56"),
        ("$1,234.56", "1234.56"),
        (" $ 1,234.56 ", "1234.56"),
        ("CAD 1,234.56", "1234.56"),
        ("-$1,234.56", "-1234.56"),
        # Accounting parentheses and a trailing sign both mean a negative.
        ("($1,234.56)", "-1234.56"),
        ("1,234.56-", "-1234.56"),
        # Scale is preserved: a printed cents column stays two places.
        ("$0.00", "0.00"),
    ],
)
def test_money_strips_how_an_amount_was_printed(printed: str, expected: str) -> None:
    assert _Amounts.model_validate({"total": printed}).total == Decimal(expected)


@pytest.mark.parametrize(
    "printed",
    ["", "n/a", "abc", "12.3.4", "1.2 or 3.4"],
    ids=["empty", "not-applicable", "words", "two-points", "two-values"],
)
def test_money_rejects_what_it_cannot_read_as_an_amount(printed: str) -> None:
    # Cleaning is deliberately narrow: what it does not recognize must fail
    # rather than be coerced into a number that was never on the page.
    with pytest.raises(ValidationError):
        _Amounts.model_validate({"total": printed})


def test_money_leaves_a_decimal_alone() -> None:
    assert _Amounts(total=Decimal("12.50")).total == Decimal("12.50")


def test_money_serializes_back_to_a_plain_decimal_string() -> None:
    # What lands in extracted_data_json, and what the frontend renders.
    extracted = _Amounts.model_validate({"total": "$1,234.56"})

    assert extracted.model_dump(mode="json") == {"total": "1234.56"}


def test_money_declares_an_unadorned_string_to_providers() -> None:
    # Decimal's own schema is an anyOf over a number and a regex-patterned
    # string; `pattern` is a keyword provider structured-output modes have
    # historically restricted. Money states the schema outright instead.
    field = _Amounts.model_json_schema()["properties"]["total"]

    assert field["type"] == "string"
    assert "anyOf" not in field
    assert "pattern" not in field
    # The encoding the plain string no longer carries has to be said somewhere.
    assert "1234.56" in field["description"]


# ================================
# --- Cashout hint declarations --
# ================================


def test_classification_hints_cover_exactly_the_registered_schemas() -> None:
    # UNKNOWN has neither a schema nor a hint; the two registries must not
    # drift apart.
    assert set(CASHOUT_CLASSIFICATION_HINTS) == set(CASHOUT_DOCUMENT_SCHEMAS)


def test_every_registered_schema_field_declares_a_hint() -> None:
    for schema in CASHOUT_DOCUMENT_SCHEMAS.values():
        hints = collect_field_hints(schema)
        assert set(hints) == set(schema.model_fields), schema.__name__


def test_registered_schemas_stay_in_the_portable_json_schema_subset() -> None:
    # Every monetary field must go through Money: a bare Decimal reintroduces
    # the anyOf/pattern shape that provider structured-output modes restrict.
    for schema in CASHOUT_DOCUMENT_SCHEMAS.values():
        rendered = json.dumps(schema.model_json_schema())
        assert "anyOf" not in rendered, schema.__name__
        assert "pattern" not in rendered, schema.__name__


def test_field_hints_stay_out_of_the_json_schema() -> None:
    # Hints must not grow the provider schema payloads (unlike Field
    # descriptions, which land in the JSON schema).
    schema = json.dumps(TouchBistroReportData.model_json_schema())
    assert "FieldHint" not in schema
    assert "Gross Sales" not in schema


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
