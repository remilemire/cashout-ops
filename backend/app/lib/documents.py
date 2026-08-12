# backend/app/lib/documents.py

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

# How much of an upload is pulled into memory per read. Bounds the peak
# allocation while reading, and keeps the overshoot past a caller's limit to at
# most one byte (see `read_document`).
CHUNK_SIZE = 1024 * 1024


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


class AsyncByteReader(Protocol):
    """The read side of an uploaded file; `fastapi.UploadFile` satisfies it."""

    async def read(self, size: int = -1, /) -> bytes: ...


async def read_document(file: AsyncByteReader, *, limit: int) -> bytes:
    """Read `file` in chunks, stopping once it grows past `limit` bytes.

    Returns at most `limit + 1` bytes, so an oversized document is never held
    in memory in full, and the caller's own `len(data) > limit` check still
    trips on the one byte of overshoot. A caller that only needs the bytes
    (not the verdict) can treat the result as the whole document.
    """
    chunks: list[bytes] = []
    size = 0

    # `limit + 1 - size` is the unread part of the budget, so the final read
    # never pulls in more than the one byte that proves the document oversized.
    while size <= limit:
        chunk = await file.read(min(CHUNK_SIZE, limit + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)

    return b"".join(chunks)


__all__ = [
    "CHUNK_SIZE",
    "AsyncByteReader",
    "DocumentContent",
    "DocumentContentType",
    "read_document",
]
