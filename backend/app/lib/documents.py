from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


# Only types the AI vision API accepts; HEIC/HEIF uploads must be converted
# client-side (or a conversion step added) before they can be supported.
class DocumentContentType(StrEnum):
    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"
    PDF = "application/pdf"


@dataclass(frozen=True)
class DocumentContent:
    data: bytes
    content_type: DocumentContentType


__all__ = ["DocumentContent", "DocumentContentType"]
