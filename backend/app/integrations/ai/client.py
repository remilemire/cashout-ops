from __future__ import annotations

from typing import Protocol, TypeAlias, TypeVar

from pydantic import BaseModel

from app.lib.documents import DocumentContent

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)
AIContent: TypeAlias = str | DocumentContent


class AIClient(Protocol):
    """Provider-neutral primitives for structured AI analysis."""

    async def analyze(
        self,
        content: AIContent,
        response_model: type[ResponseModelT],
        *,
        instructions: str | None = None,
    ) -> ResponseModelT: ...


__all__ = ["AIClient", "AIContent", "ResponseModelT"]
