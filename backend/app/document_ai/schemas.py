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
    confidence: float = Field(
        ge=0,
        le=1,
        multiple_of=0.05,
        description="Classification rubric score divided by 100, in steps of 0.05; independent of extraction confidence.",
    )


class DocumentClassification(BaseModel, Generic[ClassificationT]):
    """A resolved classification: an unclassifiable document raised instead,
    so `value` always holds one of the allowed types."""

    model_config = ConfigDict(extra="forbid")

    value: ClassificationT
    confidence: float = Field(ge=0, le=1, multiple_of=0.05)


class FieldIssue(BaseModel):
    """A field the model flagged as uncertain or inconsistent during extraction."""

    model_config = ConfigDict(extra="forbid")

    path: str
    message: str


class DocumentAnalysis(BaseModel, Generic[ResponseModelT]):
    """Structured extraction result: the typed data plus quality signals."""

    model_config = ConfigDict(extra="forbid")

    data: ResponseModelT
    confidence: float = Field(
        ge=0,
        le=1,
        multiple_of=0.05,
        description="Strict completeness and reliability score, independent of classification, in steps of 0.05. If any requested value is null because its evidence is missing or unreadable, confidence must be at most 0.20, even if other values are clear. Use 0.50–0.75 for material readings needing interpretation; above 0.75 requires complete, unambiguous evidence. Correctly returning null does not increase this score.",
    )
    # Pydantic v2 copies mutable defaults per-instance, so a bare [] is safe.
    issues: list[FieldIssue] = []


__all__ = [
    "ClassificationT",
    "DocumentAnalysis",
    "DocumentClassification",
    "DocumentClassificationResponse",
    "FieldIssue",
]
