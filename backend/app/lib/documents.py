from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DocumentContentType(StrEnum):
    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"
    PDF = "application/pdf"
    HEIC = "image/heic"
    HEIF = "image/heif"


@dataclass(frozen=True)
class DocumentContent:
    data: bytes
    content_type: DocumentContentType


__all__ = ["DocumentContent", "DocumentContentType"]
