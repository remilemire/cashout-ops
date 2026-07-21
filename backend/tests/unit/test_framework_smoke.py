# backend/tests/unit/test_framework_smoke.py

"""Framework smoke tests for the unit tier.

These prove the tier contract (auto-marker applied; support fakes importable
and usable with no database, Docker, or app) and lock each SDK-shaped fake to
the adapter surface it mirrors. They are not application coverage.
"""

from __future__ import annotations

import pytest

from app.documents import DocumentClassification
from app.features.cashout.extraction.schemas import ManualNoteData
from app.features.cashout.types import CashoutDocumentClassification
from app.integrations.ai.anthropic import AnthropicAIClient
from app.integrations.ai.gemini import GeminiAIClient
from app.integrations.ai.openai import OpenAIAIClient
from tests.support.fakes import FakeAIClient
from tests.support.fakes.sdk import (
    FakeAnthropic,
    FakeGemini,
    FakeGeminiResponse,
    FakeOpenAI,
    FakeParsedMessage,
)

Classification = DocumentClassification[CashoutDocumentClassification]


def test_unit_marker_auto_applied(request: pytest.FixtureRequest) -> None:
    assert request.node.get_closest_marker("unit") is not None


async def test_fake_ai_client_returns_canned_output_and_records_calls() -> None:
    classification = Classification(
        value=CashoutDocumentClassification.MANUAL_NOTE, confidence=0.95
    )
    ai = FakeAIClient(classification=classification)

    result = await ai.analyze(
        "some text", Classification, instructions="extra", max_tokens=512
    )

    assert result is classification
    assert ai.calls == [("some text", Classification, "extra", 512)]


async def test_fake_anthropic_matches_adapter_surface() -> None:
    note = ManualNoteData(note="ok")
    fake = FakeAnthropic(response=FakeParsedMessage("end_turn", note))
    client = AnthropicAIClient(fake, model="claude-test")  # type: ignore[arg-type]

    result = await client.analyze("text", ManualNoteData, max_tokens=512)

    assert result is note
    assert fake.messages.calls[0]["max_tokens"] == 512


async def test_fake_openai_matches_adapter_surface() -> None:
    note = ManualNoteData(note="ok")
    client = OpenAIAIClient(FakeOpenAI(parsed=note), model="gpt-test")  # type: ignore[arg-type]

    result = await client.analyze("text", ManualNoteData, max_tokens=512)

    assert result is note


async def test_fake_gemini_matches_adapter_surface() -> None:
    fake = FakeGemini(response=FakeGeminiResponse(parsed={"note": "ok"}))
    client = GeminiAIClient(fake, model="gemini-test")  # type: ignore[arg-type]

    result = await client.analyze("text", ManualNoteData, max_tokens=512)

    assert result == ManualNoteData(note="ok")
