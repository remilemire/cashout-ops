from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.ai import ResponseModelT

ClassificationT = TypeVar("ClassificationT", bound=StrEnum)


class DocumentClassificationResponse(BaseModel, Generic[ClassificationT]):
    """The provider-facing classify schema: what the AI fills in.

    `value` is nullable so the model can express "none of the allowed values
    apply"; the client resolves that into DocumentUnclassifiableError rather
    than handing the null to callers.
    """

    model_config = ConfigDict(extra="forbid")

    value: ClassificationT | None = None
    confidence: float = Field(ge=0, le=1)


class DocumentClassification(BaseModel, Generic[ClassificationT]):
    """A resolved classification: an unclassifiable document raised instead,
    so `value` always holds one of the allowed types."""

    model_config = ConfigDict(extra="forbid")

    value: ClassificationT
    confidence: float = Field(ge=0, le=1)


class FieldIssue(BaseModel):
    """A field the model flagged as uncertain or inconsistent during extraction."""

    model_config = ConfigDict(extra="forbid")

    path: str
    message: str


class DocumentAnalysis(BaseModel, Generic[ResponseModelT]):
    """Structured extraction result: the typed data plus quality signals."""

    model_config = ConfigDict(extra="forbid")

    data: ResponseModelT
    confidence: float = Field(ge=0, le=1)
    # Pydantic v2 copies mutable defaults per-instance, so a bare [] is safe.
    issues: list[FieldIssue] = []


__all__ = [
    "ClassificationT",
    "DocumentAnalysis",
    "DocumentClassification",
    "DocumentClassificationResponse",
    "FieldIssue",
]
