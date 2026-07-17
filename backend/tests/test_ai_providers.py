# backend/tests/test_ai_providers.py

"""Unit tests for the OpenAI and Gemini AIClient implementations.

Like the Anthropic client tests, these exercise the request/response mapping
against fakes — not the live provider APIs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import cast

import pytest
from google.genai import types
from google.genai.errors import APIError
from openai import OpenAIError

from app.features.cashout.extraction.schemas import ManualNoteData
from app.integrations.ai import AIAnalysisError, AIErrorCode
from app.integrations.ai.gemini import (
    GeminiAIClient,
    _to_part,  # pyright: ignore[reportPrivateUsage]
)
from app.integrations.ai.openai import (
    OpenAIAIClient,
    _to_content_part,  # pyright: ignore[reportPrivateUsage]
)
from app.lib.documents import DocumentContent, DocumentContentType

# ================================
# ------------ OpenAI ------------
# ================================


@dataclass
class _OAMessage:
    parsed: object | None
    refusal: str | None = None


@dataclass
class _OACompletion:
    choices: list[object]


class _OACompletions:
    def __init__(
        self,
        *,
        parsed: object | None = None,
        refusal: str | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._parsed = parsed
        self._refusal = refusal
        self._exc = exc
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> _OACompletion:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        message = _OAMessage(parsed=self._parsed, refusal=self._refusal)
        return _OACompletion(choices=[SimpleNamespace(message=message)])


class _FakeOpenAI:
    def __init__(
        self,
        *,
        parsed: object | None = None,
        refusal: str | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.chat = SimpleNamespace(
            completions=_OACompletions(parsed=parsed, refusal=refusal, exc=exc)
        )


def _openai_client(**kwargs: object) -> OpenAIAIClient:
    return OpenAIAIClient(_FakeOpenAI(**kwargs), model="gpt-test")  # type: ignore[arg-type]


async def test_openai_returns_parsed_output() -> None:
    note = ManualNoteData(note="ok")
    client = _openai_client(parsed=note)

    result = await client.analyze("text", ManualNoteData, instructions="EXTRA")

    assert result is note


async def test_openai_raises_on_refusal() -> None:
    client = _openai_client(refusal="cannot help with that")

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData)
    assert exc_info.value.code is AIErrorCode.REFUSED


async def test_openai_raises_when_no_parsed_output() -> None:
    client = _openai_client(parsed=None)

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData)
    assert exc_info.value.code is AIErrorCode.INVALID_RESPONSE


async def test_openai_wraps_provider_errors() -> None:
    client = _openai_client(exc=OpenAIError("boom"))

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData)
    assert exc_info.value.code is AIErrorCode.PROVIDER_ERROR


async def test_openai_sends_base_instructions() -> None:
    fake = _FakeOpenAI(parsed=ManualNoteData(note="ok"))
    client = OpenAIAIClient(fake, model="gpt-test")  # type: ignore[arg-type]

    await client.analyze("text", ManualNoteData, instructions="EXTRA CONTEXT")

    messages = fake.chat.completions.calls[0]["messages"]
    assert isinstance(messages, list)
    system = str(cast(dict[str, object], messages[0])["content"])
    assert "document-analysis assistant" in system
    assert "EXTRA CONTEXT" in system


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


@dataclass
class _GResponse:
    parsed: object | None = None
    candidates: list[object] = field(default_factory=list[object])
    prompt_feedback: object | None = None


class _GModels:
    def __init__(
        self, *, response: _GResponse | None = None, exc: Exception | None = None
    ) -> None:
        self._response = response
        self._exc = exc
        self.calls: list[dict[str, object]] = []

    async def generate_content(self, **kwargs: object) -> _GResponse:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response


class _FakeGemini:
    def __init__(
        self, *, response: _GResponse | None = None, exc: Exception | None = None
    ) -> None:
        self.aio = SimpleNamespace(models=_GModels(response=response, exc=exc))


def _gemini_client(**kwargs: object) -> GeminiAIClient:
    return GeminiAIClient(_FakeGemini(**kwargs), model="gemini-test")  # type: ignore[arg-type]


async def test_gemini_returns_parsed_output() -> None:
    note = ManualNoteData(note="ok")
    client = _gemini_client(response=_GResponse(parsed=note))

    result = await client.analyze("text", ManualNoteData)

    assert result is note


async def test_gemini_raises_on_safety_finish_reason() -> None:
    response = _GResponse(
        parsed=None,
        candidates=[SimpleNamespace(finish_reason=types.FinishReason.SAFETY)],
    )
    client = _gemini_client(response=response)

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData)
    assert exc_info.value.code is AIErrorCode.REFUSED


async def test_gemini_raises_on_blocked_prompt() -> None:
    response = _GResponse(
        prompt_feedback=SimpleNamespace(block_reason=SimpleNamespace(name="SAFETY"))
    )
    client = _gemini_client(response=response)

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData)
    assert exc_info.value.code is AIErrorCode.REFUSED


async def test_gemini_raises_when_no_parsed_output() -> None:
    client = _gemini_client(response=_GResponse(parsed=None))

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData)
    assert exc_info.value.code is AIErrorCode.INVALID_RESPONSE


async def test_gemini_wraps_provider_errors() -> None:
    client = _gemini_client(
        exc=APIError(500, {"message": "boom", "status": "INTERNAL"})
    )

    with pytest.raises(AIAnalysisError) as exc_info:
        await client.analyze("text", ManualNoteData)
    assert exc_info.value.code is AIErrorCode.PROVIDER_ERROR


def test_gemini_part_maps_pdf_mime_type() -> None:
    part = _to_part(DocumentContent(data=b"pdf", content_type=DocumentContentType.PDF))
    assert part.inline_data is not None
    assert part.inline_data.mime_type == "application/pdf"
