# backend/app/integrations/ai/anthropic.py

from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Literal

from anthropic import APIError, AsyncAnthropic
from anthropic.types import (
    Base64ImageSourceParam,
    Base64PDFSourceParam,
    DocumentBlockParam,
    ImageBlockParam,
)
from pydantic import ValidationError

from app.core.ai import AIProvider
from app.lib.documents import DocumentContent, DocumentContentType

from .client import AIContent, ResponseModelT
from .errors import AIAnalysisError, AIErrorCode
from .instructions import BASE_INSTRUCTIONS, compose_instructions

_IMAGE_MEDIA_TYPES: Mapping[
    DocumentContentType, Literal["image/jpeg", "image/png", "image/webp"]
] = {
    DocumentContentType.JPEG: "image/jpeg",
    DocumentContentType.PNG: "image/png",
    DocumentContentType.WEBP: "image/webp",
}


class AnthropicAIClient:
    """`AIClient` backed by the Anthropic Messages API."""

    provider: AIProvider = AIProvider.ANTHROPIC

    def __init__(self, client: AsyncAnthropic, *, model: str) -> None:
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
        try:
            response = await self._client.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                thinking={"type": "adaptive"},
                system=compose_instructions(BASE_INSTRUCTIONS, instructions),
                messages=[{"role": "user", "content": _to_message_content(content)}],
                output_format=response_model,
            )
        except APIError as exc:
            raise AIAnalysisError(AIErrorCode.SERVICE_UNAVAILABLE, str(exc)) from exc
        except ValidationError as exc:
            raise AIAnalysisError(AIErrorCode.UNREADABLE_DOCUMENT, str(exc)) from exc

        if response.stop_reason == "refusal":
            raise AIAnalysisError(
                AIErrorCode.DOCUMENT_REJECTED,
                "The provider declined to analyze this content.",
            )
        # Checked before parsed_output: truncated output also fails to parse,
        # and the max_tokens stop reason is the more actionable signal.
        if response.stop_reason == "max_tokens":
            raise AIAnalysisError(
                AIErrorCode.OUTPUT_LIMIT_REACHED,
                "The response hit the max_tokens limit before completing.",
            )

        parsed = response.parsed_output
        if parsed is None:
            raise AIAnalysisError(
                AIErrorCode.UNREADABLE_DOCUMENT,
                "The response did not contain valid structured output.",
            )
        return parsed


def _to_message_content(
    content: AIContent,
) -> str | list[ImageBlockParam | DocumentBlockParam]:
    if isinstance(content, str):
        return content
    return [_to_document_block(content)]


def _to_document_block(
    content: DocumentContent,
) -> ImageBlockParam | DocumentBlockParam:
    data = base64.standard_b64encode(content.data).decode()

    if content.content_type is DocumentContentType.PDF:
        return DocumentBlockParam(
            type="document",
            source=Base64PDFSourceParam(
                type="base64", media_type="application/pdf", data=data
            ),
        )

    media_type = _IMAGE_MEDIA_TYPES.get(content.content_type)
    if media_type is None:
        raise AIAnalysisError(
            AIErrorCode.UNSUPPORTED_FILE_TYPE,
            f"Content type {content.content_type.value} is not supported for AI analysis.",
        )
    return ImageBlockParam(
        type="image",
        source=Base64ImageSourceParam(type="base64", media_type=media_type, data=data),
    )


__all__ = ["AnthropicAIClient"]
