# backend/tests/support/fakes/sdk/gemini.py

"""Fakes shaped like the `genai.Client` surface `GeminiAIClient` uses.

The adapter (`app/integrations/ai/gemini.py`) calls
`client.aio.models.generate_content(...)` and reads `parsed`, `candidates`
(each with `finish_reason`), and `prompt_feedback` (with `block_reason`) off
the response. Pass a `FakeGemini` where the adapter expects `genai.Client`.

`FakeCandidate.finish_reason` and `FakePromptFeedback.block_reason` accept any
object; integration-adjacent tests can pass real `google.genai.types` members.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeCandidate:
    finish_reason: object | None = None


@dataclass
class FakePromptFeedback:
    block_reason: object | None = None


@dataclass
class FakeGeminiResponse:
    parsed: object | None = None
    candidates: list[object] = field(default_factory=list[object])
    prompt_feedback: object | None = None


class FakeModels:
    def __init__(
        self,
        *,
        response: FakeGeminiResponse | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._response = response
        self._exc = exc
        self.calls: list[dict[str, object]] = []

    async def generate_content(self, **kwargs: object) -> FakeGeminiResponse:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        assert self._response is not None, "FakeGemini has no configured response"
        return self._response


@dataclass
class _FakeAio:
    models: FakeModels


class FakeGemini:
    def __init__(
        self,
        *,
        response: FakeGeminiResponse | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.aio = _FakeAio(models=FakeModels(response=response, exc=exc))
