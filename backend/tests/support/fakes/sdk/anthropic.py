# backend/tests/support/fakes/sdk/anthropic.py

"""Fakes shaped like the `AsyncAnthropic` surface `AnthropicAIClient` uses.

The adapter (`app/integrations/ai/anthropic.py`) calls
`client.messages.parse(...)` and reads `stop_reason` / `parsed_output` off the
result. Pass a `FakeAnthropic` where the adapter expects `AsyncAnthropic`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel


@dataclass
class FakeParsedMessage:
    stop_reason: str
    parsed_output: BaseModel | None


class FakeMessages:
    def __init__(
        self,
        *,
        response: FakeParsedMessage | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._response = response
        self._exc = exc
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs: object) -> FakeParsedMessage:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        assert self._response is not None, "FakeAnthropic has no configured response"
        return self._response


class FakeAnthropic:
    def __init__(
        self,
        *,
        response: FakeParsedMessage | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.messages = FakeMessages(response=response, exc=exc)
