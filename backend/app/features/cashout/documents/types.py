# backend/app/features/cashout/documents/types.py

from __future__ import annotations

from dataclasses import dataclass

from app.lib.documents import DocumentContentType


@dataclass(frozen=True)
class DocumentUpload:
    data: bytes
    content_type: DocumentContentType
    original_filename: str


__all__ = ["DocumentUpload"]
