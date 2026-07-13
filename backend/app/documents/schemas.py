from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

ClassificationT = TypeVar("ClassificationT", bound=StrEnum)


class DocumentClassification(BaseModel, Generic[ClassificationT]):
    model_config = ConfigDict(extra="forbid")

    value: ClassificationT
    confidence: float = Field(ge=0, le=1)


__all__ = ["ClassificationT", "DocumentClassification"]
