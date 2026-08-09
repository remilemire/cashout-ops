# backend/app/integrations/ai/gemini.py

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


class GeminiAIClient:
    """`AIClient` backed by the Google Gemini API (structured output).

    Note: exercised only against fakes in the test suite — not yet verified
    against the live Gemini API.
    """

    provider: AIProvider = AIProvider.GEMINI

    def __init__(self, client: genai.Client, *, model: str) -> None:
        self._client = client
        self.model = model

    async def analyze(
        self,
        content: AIContent,
        response_model: type[ResponseModelT],
        *,
        instructions: str | None = None,
        max_tokens: int,
    ) -> ResponseModelT:
        config = types.GenerateContentConfig(
            system_instruction=compose_instructions(BASE_INSTRUCTIONS, instructions),
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            # Must be response_json_schema, not response_schema: the response
            # models set extra="forbid", so their JSON schema carries
            # additionalProperties, which the typed response_schema path
            # rejects. The trade-off: the SDK no longer instantiates the model
            # — response.parsed holds the decoded JSON dict, validated below.
            response_json_schema=response_model.model_json_schema(),
        )

        try:
            # google-genai rebinds its `PartUnion` type alias inside a runtime
            # `if _is_pillow_image_imported` block, so pyright can't resolve it and
            # flags generate_content as partially unknown. The call and its typed
            # result are fine; suppress only that member-type diagnostic.
            response = await self._client.aio.models.generate_content(  # pyright: ignore[reportUnknownMemberType]
                model=self.model,
                contents=_to_contents(content),
                config=config,
            )
        except APIError as exc:
            raise AIAnalysisError(AIErrorCode.SERVICE_UNAVAILABLE, str(exc)) from exc

        _raise_if_unusable(response)

        parsed = response.parsed
        if not isinstance(parsed, dict):
            raise AIAnalysisError(
                AIErrorCode.UNREADABLE_DOCUMENT,
                "The response did not contain valid structured output.",
            )
        try:
            return response_model.model_validate(parsed)
        except ValidationError as exc:
            raise AIAnalysisError(AIErrorCode.UNREADABLE_DOCUMENT, str(exc)) from exc


def _to_contents(content: AIContent) -> list[str | types.Part]:
    if isinstance(content, str):
        return [content]
    return [_to_part(content)]


def _to_part(content: DocumentContent) -> types.Part:
    return types.Part.from_bytes(
        data=content.data, mime_type=content.content_type.value
    )


def _raise_if_unusable(response: types.GenerateContentResponse) -> None:
    """Blocked prompts, refusal finish reasons, and truncation all abort."""
    feedback = response.prompt_feedback
    if feedback is not None and feedback.block_reason is not None:
        raise AIAnalysisError(
            AIErrorCode.DOCUMENT_REJECTED,
            f"Prompt blocked: {feedback.block_reason.name}",
        )

    for candidate in response.candidates or []:
        finish_reason = candidate.finish_reason
        if finish_reason is None:
            continue
        if finish_reason == types.FinishReason.MAX_TOKENS:
            raise AIAnalysisError(
                AIErrorCode.OUTPUT_LIMIT_REACHED,
                "The response hit the max output tokens limit before completing.",
            )
        if finish_reason in _REFUSAL_FINISH_REASONS:
            raise AIAnalysisError(
                AIErrorCode.DOCUMENT_REJECTED,
                f"The provider declined to analyze this content "
                f"({finish_reason.name}).",
            )


__all__ = ["GeminiAIClient"]
