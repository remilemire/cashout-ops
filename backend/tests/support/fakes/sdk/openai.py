# backend/tests/support/fakes/sdk/openai.py

"""Fakes shaped like the `AsyncOpenAI` surface `OpenAIAIClient` uses.

The adapter (`app/integrations/ai/openai.py`) calls
`client.chat.completions.parse(...)` and reads `parsed` / `refusal` off
`choices[0].message`. Pass a `FakeOpenAI` where the adapter expects
`AsyncOpenAI`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FakeMessage:
    parsed: object | None
    refusal: str | None = None


@dataclass
class _FakeChoice:
    message: FakeMessage


@dataclass
class FakeCompletion:
    choices: list[_FakeChoice]


class FakeCompletions:
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

    async def parse(self, **kwargs: object) -> FakeCompletion:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        message = FakeMessage(parsed=self._parsed, refusal=self._refusal)
        return FakeCompletion(choices=[_FakeChoice(message=message)])


@dataclass
class _FakeChat:
    completions: FakeCompletions


class FakeOpenAI:
    def __init__(
        self,
        *,
        parsed: object | None = None,
        refusal: str | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.chat = _FakeChat(
            completions=FakeCompletions(parsed=parsed, refusal=refusal, exc=exc)
        )


__all__ = ["FakeCompletion", "FakeCompletions", "FakeMessage", "FakeOpenAI"]
