# backend/app/features/cashout/uploads/types.py

from __future__ import annotations

from dataclasses import dataclass

from app.lib.documents import DocumentContentType


@dataclass(frozen=True)
class UploadPayload:
    """The file as received: its bytes, declared type, and client filename."""

    data: bytes
    content_type: DocumentContentType
    original_filename: str


__all__ = ["UploadPayload"]
