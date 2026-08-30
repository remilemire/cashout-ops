# backend/app/integrations/ai/openai.py

from __future__ import annotations

import base64

from openai import AsyncOpenAI, LengthFinishReasonError, OpenAIError
from openai.types.chat import ChatCompletionContentPartParam, ChatCompletionMessageParam
from pydantic import ValidationError

from app.core.providers import AIProvider
from app.lib.documents import DocumentContent, DocumentContentType

from .client import AIContent, ResponseModelT
from .errors import AIAnalysisError, AIErrorCode
from .instructions import BASE_INSTRUCTIONS, compose_instructions


class OpenAIAIClient:
    """`AIClient` backed by the OpenAI Chat Completions API (structured output).

    Note: exercised only against fakes in the test suite — not yet verified
    against the live OpenAI API.
    """

    provider: AIProvider = AIProvider.OPENAI

    def __init__(self, client: AsyncOpenAI, *, model: str) -> None:
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
        messages: list[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": compose_instructions(BASE_INSTRUCTIONS, instructions),
            },
            {"role": "user", "content": _to_user_content(content)},
        ]

        try:
            completion = await self._client.chat.completions.parse(
                model=self.model,
                max_completion_tokens=max_tokens,
                messages=messages,
                response_format=response_model,
            )
        # The SDK raises this itself when finish_reason is "length"; it
        # subclasses OpenAIError, so it must be caught first or truncation
        # would be misreported as a provider error.
        except LengthFinishReasonError as exc:
            raise AIAnalysisError(
                AIErrorCode.OUTPUT_LIMIT_REACHED,
                "The response hit the token limit before completing.",
            ) from exc
        except OpenAIError as exc:
            raise AIAnalysisError(AIErrorCode.SERVICE_UNAVAILABLE, str(exc)) from exc
        except ValidationError as exc:
            raise AIAnalysisError(AIErrorCode.INVALID_RESPONSE, str(exc)) from exc

        message = completion.choices[0].message
        if message.refusal:
            raise AIAnalysisError(AIErrorCode.CONTENT_REFUSED, message.refusal)

        if message.parsed is None:
            raise AIAnalysisError(
                AIErrorCode.INVALID_RESPONSE,
                "The response did not contain valid structured output.",
            )
        return message.parsed


def _to_user_content(
    content: AIContent,
) -> str | list[ChatCompletionContentPartParam]:
    if isinstance(content, str):
        return content
    return [_to_content_part(content)]


def _to_content_part(content: DocumentContent) -> ChatCompletionContentPartParam:
    data = base64.standard_b64encode(content.data).decode()
    data_url = f"data:{content.content_type.value};base64,{data}"

    if content.content_type is DocumentContentType.PDF:
        return {
            "type": "file",
            "file": {"filename": "document.pdf", "file_data": data_url},
        }
    return {"type": "image_url", "image_url": {"url": data_url}}


__all__ = ["OpenAIAIClient"]
