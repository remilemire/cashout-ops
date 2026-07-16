from __future__ import annotations

import base64

from openai import AsyncOpenAI, OpenAIError
from openai.types.chat import ChatCompletionContentPartParam, ChatCompletionMessageParam
from pydantic import ValidationError

from app.lib.documents import DocumentContent, DocumentContentType

from .client import AIContent, ResponseModelT
from .errors import AIAnalysisError, AIErrorCode
from .instructions import BASE_INSTRUCTIONS, compose_instructions
from .types import AIProvider


class OpenAIAIClient:
    """`AIClient` backed by the OpenAI Chat Completions API (structured output).

    Note: exercised only against fakes in the test suite — not yet verified
    against the live OpenAI API.
    """

    provider: AIProvider = AIProvider.OPENAI

    def __init__(
        self, client: AsyncOpenAI, *, model: str, max_tokens: int = 16000
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
                max_completion_tokens=self._max_tokens,
                messages=messages,
                response_format=response_model,
            )
        except OpenAIError as exc:
            raise AIAnalysisError(AIErrorCode.PROVIDER_ERROR, str(exc)) from exc
        except ValidationError as exc:
            raise AIAnalysisError(AIErrorCode.INVALID_RESPONSE, str(exc)) from exc

        message = completion.choices[0].message
        if message.refusal:
            raise AIAnalysisError(AIErrorCode.REFUSED, message.refusal)

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
