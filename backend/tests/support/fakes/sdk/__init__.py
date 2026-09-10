"""SDK-shaped fakes for unit-testing the provider `AIClient` adapters.

Each module mirrors the exact surface its adapter in `app/integrations/ai/`
touches on the real SDK client — nothing from the real SDKs is imported, so
these are safe in the unit tier. Every fake records call kwargs in `.calls`
for request-shaping assertions.
"""

from .anthropic import FakeAnthropic, FakeMessages, FakeParsedMessage
from .gemini import (
    FakeCandidate,
    FakeGemini,
    FakeGeminiResponse,
    FakeModels,
    FakePromptFeedback,
)
from .openai import FakeCompletion, FakeCompletions, FakeMessage, FakeOpenAI

__all__ = [
    "FakeAnthropic",
    "FakeCandidate",
    "FakeCompletion",
    "FakeCompletions",
    "FakeGemini",
    "FakeGeminiResponse",
    "FakeMessage",
    "FakeMessages",
    "FakeModels",
    "FakeOpenAI",
    "FakeParsedMessage",
    "FakePromptFeedback",
]
