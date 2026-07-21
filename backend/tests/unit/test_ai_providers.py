# backend/tests/unit/test_ai_providers.py

"""Unit tests for the Anthropic, OpenAI, and Gemini AIClient implementations.

These exercise each provider's request/response mapping against the SDK-shaped
fakes in tests.support.fakes.sdk — not the live provider APIs.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from anthropic import APIError as AnthropicAPIError
from google.genai import types
from google.genai.errors import APIError
from openai import LengthFinishReasonError, OpenAIError
from openai.types.chat import ChatCompletion

from app.features.cashout.extraction.schemas import ManualNoteData
from app.integrations.ai import AIAnalysisError, AIErrorCode
from app.integrations.ai.anthropic import (
    AnthropicAIClient,
    _to_document_block,  # pyright: ignore[reportPrivateUsage]
)
from app.integrations.ai.gemini import (
    GeminiAIClient,
    _to_part,  # pyright: ignore[reportPrivateUsage]
)
from app.integrations.ai.openai import (
    OpenAIAIClient,
    _to_content_part,  # pyright: ignore[reportPrivateUsage]
)
from app.lib.documents import DocumentContent, DocumentContentType
from tests.support.fakes.sdk import (
    FakeAnthropic,
    FakeCandidate,
    FakeGemini,
    FakeGeminiResponse,
    FakeOpenAI,
    FakeParsedMessage,
    FakePromptFeedback,
)

# ================================
# ---------- Anthropic -----------
# ================================


def _anthropic_client(**kwargs: object) -> AnthropicAIClient:
    fake = FakeAnthropic(**kwargs)  # type: ignore[arg-type]
    return AnthropicAIClient(fake, model="claude-test")  # type: ignore[arg-type]


async def test_anthropic_returns_parsed_output() -> None:
    note = ManualNoteData(note="ok")
    client = _anthropic_client(response=FakeParsedMessage("end_turn", note))

    result = await client.analyze(
        DocumentContent(data=b"pdf", content_type=DocumentContentType.PDF),
        ManualNoteData,
        max_tokens=512,
    )

    assert result is note


async def test_anthropic_raises_on_refusal() -> None:
    client = _anthropic_client(response=FakeParsedMessage("refusal", None))

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze(
            DocumentContent(data=b"pdf", content_type=DocumentContentType.PDF),
            ManualNoteData,
            max_tokens=512,
        )
    assert exc_info.value.code is AIErrorCode.REFUSED


async def test_anthropic_raises_on_truncated_output() -> None:
    client = _anthropic_client(response=FakeParsedMessage("max_tokens", None))

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData, max_tokens=512)
    assert exc_info.value.code is AIErrorCode.TRUNCATED


async def test_anthropic_raises_when_no_parsed_output() -> None:
    client = _anthropic_client(response=FakeParsedMessage("end_turn", None))

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("some text", ManualNoteData, max_tokens=512)
    assert exc_info.value.code is AIErrorCode.INVALID_RESPONSE


async def test_anthropic_wraps_provider_errors() -> None:
    api_error = AnthropicAPIError(
        "boom", request=httpx.Request("POST", "http://test"), body=None
    )
    client = _anthropic_client(exc=api_error)

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData, max_tokens=512)
    assert exc_info.value.code is AIErrorCode.PROVIDER_ERROR


async def test_anthropic_sends_base_instructions() -> None:
    fake = FakeAnthropic(
        response=FakeParsedMessage("end_turn", ManualNoteData(note="ok"))
    )
    client = AnthropicAIClient(fake, model="claude-test")  # type: ignore[arg-type]

    await client.analyze(
        "text", ManualNoteData, instructions="EXTRA CONTEXT", max_tokens=512
    )

    system = fake.messages.calls[0]["system"]
    assert isinstance(system, str)
    assert (
        "application-controlled AI component" in system
    )  # base persona always present
    assert "EXTRA CONTEXT" in system  # caller instructions appended
    assert fake.messages.calls[0]["max_tokens"] == 512  # per-call budget


def test_anthropic_document_block_maps_pdf() -> None:
    block = _to_document_block(
        DocumentContent(data=b"pdf-bytes", content_type=DocumentContentType.PDF)
    )

    assert block["type"] == "document"
    assert cast(dict[str, object], block["source"])["media_type"] == "application/pdf"


def test_anthropic_document_block_maps_image() -> None:
    block = _to_document_block(
        DocumentContent(data=b"png-bytes", content_type=DocumentContentType.PNG)
    )

    assert block["type"] == "image"
    assert cast(dict[str, object], block["source"])["media_type"] == "image/png"


# ================================
# ------------ OpenAI ------------
# ================================


def _openai_client(**kwargs: object) -> OpenAIAIClient:
    return OpenAIAIClient(FakeOpenAI(**kwargs), model="gpt-test")  # type: ignore[arg-type]


async def test_openai_returns_parsed_output() -> None:
    note = ManualNoteData(note="ok")
    client = _openai_client(parsed=note)

    result = await client.analyze(
        "text", ManualNoteData, instructions="EXTRA", max_tokens=512
    )

    assert result is note


async def test_openai_raises_on_refusal() -> None:
    client = _openai_client(refusal="cannot help with that")

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData, max_tokens=512)
    assert exc_info.value.code is AIErrorCode.REFUSED


async def test_openai_raises_when_no_parsed_output() -> None:
    client = _openai_client(parsed=None)

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData, max_tokens=512)
    assert exc_info.value.code is AIErrorCode.INVALID_RESPONSE


async def test_openai_raises_on_truncated_output() -> None:
    # The SDK raises LengthFinishReasonError from parse() itself when
    # finish_reason is "length"; its __init__ only reads completion.usage.
    truncated = LengthFinishReasonError(
        completion=cast(ChatCompletion, SimpleNamespace(usage=None))
    )
    client = _openai_client(exc=truncated)

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData, max_tokens=512)
    assert exc_info.value.code is AIErrorCode.TRUNCATED


async def test_openai_wraps_provider_errors() -> None:
    client = _openai_client(exc=OpenAIError("boom"))

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData, max_tokens=512)
    assert exc_info.value.code is AIErrorCode.PROVIDER_ERROR


async def test_openai_sends_base_instructions() -> None:
    fake = FakeOpenAI(parsed=ManualNoteData(note="ok"))
    client = OpenAIAIClient(fake, model="gpt-test")  # type: ignore[arg-type]

    await client.analyze(
        "text", ManualNoteData, instructions="EXTRA CONTEXT", max_tokens=512
    )

    messages = fake.chat.completions.calls[0]["messages"]
    assert isinstance(messages, list)
    system = str(cast(dict[str, object], messages[0])["content"])
    assert "application-controlled AI component" in system
    assert "EXTRA CONTEXT" in system
    assert fake.chat.completions.calls[0]["max_completion_tokens"] == 512


def test_openai_content_part_maps_pdf() -> None:
    part = _to_content_part(
        DocumentContent(data=b"pdf", content_type=DocumentContentType.PDF)
    )
    assert part["type"] == "file"


def test_openai_content_part_maps_image() -> None:
    part = _to_content_part(
        DocumentContent(data=b"png", content_type=DocumentContentType.PNG)
    )
    assert part["type"] == "image_url"
    assert part["image_url"]["url"].startswith("data:image/png;base64,")


# ================================
# ------------ Gemini ------------
# ================================


def _gemini_client(**kwargs: object) -> GeminiAIClient:
    return GeminiAIClient(FakeGemini(**kwargs), model="gemini-test")  # type: ignore[arg-type]


async def test_gemini_validates_parsed_dict_into_model() -> None:
    # With response_json_schema the SDK returns the decoded dict, not a model
    # instance; the client does the validation itself.
    fake = FakeGemini(response=FakeGeminiResponse(parsed={"note": "ok"}))
    client = GeminiAIClient(fake, model="gemini-test")  # type: ignore[arg-type]

    result = await client.analyze("text", ManualNoteData, max_tokens=512)

    assert result == ManualNoteData(note="ok")

    # response_json_schema (not response_schema): the models' extra="forbid"
    # emits additionalProperties, which response_schema rejects.
    config = fake.aio.models.calls[0]["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.response_json_schema == ManualNoteData.model_json_schema()
    # google-genai types response_schema with a partially-unknown union; the
    # access is safe (we only compare to None). Same SDK gap as gemini.py.
    assert config.response_schema is None  # pyright: ignore[reportUnknownMemberType]
    assert config.max_output_tokens == 512  # per-call budget


async def test_gemini_raises_when_parsed_dict_fails_validation() -> None:
    client = _gemini_client(response=FakeGeminiResponse(parsed={"unexpected": "field"}))

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData, max_tokens=512)
    assert exc_info.value.code is AIErrorCode.INVALID_RESPONSE


async def test_gemini_raises_on_safety_finish_reason() -> None:
    response = FakeGeminiResponse(
        parsed=None,
        candidates=[FakeCandidate(finish_reason=types.FinishReason.SAFETY)],
    )
    client = _gemini_client(response=response)

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData, max_tokens=512)
    assert exc_info.value.code is AIErrorCode.REFUSED


async def test_gemini_raises_on_truncated_output() -> None:
    response = FakeGeminiResponse(
        parsed=None,
        candidates=[FakeCandidate(finish_reason=types.FinishReason.MAX_TOKENS)],
    )
    client = _gemini_client(response=response)

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData, max_tokens=512)
    assert exc_info.value.code is AIErrorCode.TRUNCATED


async def test_gemini_raises_on_blocked_prompt() -> None:
    response = FakeGeminiResponse(
        prompt_feedback=FakePromptFeedback(block_reason=SimpleNamespace(name="SAFETY"))
    )
    client = _gemini_client(response=response)

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData, max_tokens=512)
    assert exc_info.value.code is AIErrorCode.REFUSED


async def test_gemini_raises_when_no_parsed_output() -> None:
    client = _gemini_client(response=FakeGeminiResponse(parsed=None))

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData, max_tokens=512)
    assert exc_info.value.code is AIErrorCode.INVALID_RESPONSE


async def test_gemini_wraps_provider_errors() -> None:
    client = _gemini_client(
        exc=APIError(500, {"message": "boom", "status": "INTERNAL"})
    )

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData, max_tokens=512)
    assert exc_info.value.code is AIErrorCode.PROVIDER_ERROR


def test_gemini_part_maps_pdf_mime_type() -> None:
    part = _to_part(DocumentContent(data=b"pdf", content_type=DocumentContentType.PDF))
    assert part.inline_data is not None
    assert part.inline_data.mime_type == "application/pdf"
