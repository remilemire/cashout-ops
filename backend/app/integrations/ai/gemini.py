from __future__ import annotations

from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import ValidationError

from app.lib.documents import DocumentContent

from .client import AIContent, ResponseModelT
from .errors import AIAnalysisError, AIErrorCode
from .instructions import BASE_INSTRUCTIONS, compose_instructions
from .types import AIProvider

# Finish reasons that mean the model declined rather than completed.
_REFUSAL_FINISH_REASONS = frozenset(
    {
        types.FinishReason.SAFETY,
        types.FinishReason.RECITATION,
        types.FinishReason.BLOCKLIST,
        types.FinishReason.PROHIBITED_CONTENT,
        types.FinishReason.SPII,
        types.FinishReason.IMAGE_SAFETY,
    }
)


# AGENT: I'm getting quite a view vscode pylance errors as indicated by the comments


class GeminiAIClient:
    """`AIClient` backed by the Google Gemini API (structured output).

    Note: exercised only against fakes in the test suite — not yet verified
    against the live Gemini API.
    """

    provider: AIProvider = AIProvider.GEMINI

    def __init__(
        self, client: genai.Client, *, model: str, max_tokens: int = 16000
    ) -> None:
        self._client = client
        self.model = model
        self._max_tokens = max_tokens

    async def analyze(
        self,
        content: AIContent,
        response_model: type[ResponseModelT],
        *,
        instructions: str | None = None,
    ) -> ResponseModelT:
        config = types.GenerateContentConfig(
            system_instruction=compose_instructions(BASE_INSTRUCTIONS, instructions),
            max_output_tokens=self._max_tokens,
            response_mime_type="application/json",
            response_schema=response_model,
        )

        try:
            response = await self._client.aio.models.generate_content(  # Type of "generate_content" is partially unknown
                model=self.model,
                contents=_to_contents(content),
                config=config,
            )
        except APIError as exc:
            raise AIAnalysisError(AIErrorCode.PROVIDER_ERROR, str(exc)) from exc
        except ValidationError as exc:
            raise AIAnalysisError(AIErrorCode.INVALID_RESPONSE, str(exc)) from exc

        _raise_if_refused(response)

        parsed = response.parsed
        if not isinstance(parsed, response_model):
            raise AIAnalysisError(
                AIErrorCode.INVALID_RESPONSE,
                "The response did not contain valid structured output.",
            )
        return parsed


def _to_contents(
    content: AIContent,
) -> list[
    types.PartUnionDict
]:  # Return type, "list[Unknown]", is partially unknown, Type of "PartUnionDict" is unknown
    if isinstance(content, str):
        return [content]  # Return type, "list[Unknown]", is partially unknown
    return [_to_part(content)]  # Return type, "list[Unknown]", is partially unknown


def _to_part(content: DocumentContent) -> types.Part:
    return types.Part.from_bytes(
        data=content.data, mime_type=content.content_type.value
    )


def _raise_if_refused(response: types.GenerateContentResponse) -> None:
    feedback = response.prompt_feedback
    if feedback is not None and feedback.block_reason is not None:
        raise AIAnalysisError(
            AIErrorCode.REFUSED, f"Prompt blocked: {feedback.block_reason.name}"
        )

    for candidate in response.candidates or []:
        if candidate.finish_reason in _REFUSAL_FINISH_REASONS:
            raise AIAnalysisError(
                AIErrorCode.REFUSED,
                f"The provider declined to analyze this content "
                f"({candidate.finish_reason.name}).",  # "name" is not a known attribute of "None"
            )


__all__ = ["GeminiAIClient"]
