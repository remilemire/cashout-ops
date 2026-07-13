from __future__ import annotations

from dataclasses import dataclass

from app.lib.documents import DocumentContentType


@dataclass(frozen=True)
class DocumentRef:
    storage_key: str
    content_type: DocumentContentType


__all__ = ["DocumentRef"]
