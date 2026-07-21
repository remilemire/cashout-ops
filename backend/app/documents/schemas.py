# backend/app/documents/schemas.py

from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.ai import ResponseModelT

ClassificationT = TypeVar("ClassificationT", bound=StrEnum)


class DocumentClassification(BaseModel, Generic[ClassificationT]):
    model_config = ConfigDict(extra="forbid")

    # Null when none of the allowed values apply (the document is unclassifiable).
    value: ClassificationT | None = None
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
    "FieldIssue",
]
