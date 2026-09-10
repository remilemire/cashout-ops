from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

# Maximum requested bytes per read; accumulated chunks also consume memory.
CHUNK_SIZE = 1024 * 1024


# Supported upload formats. HEIC/HEIF require conversion before upload;
# provider adapters may impose additional format restrictions.
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
    """Read up to `limit + 1` bytes from a file, in bounded chunks.

    Callers must reject a result longer than `limit`: it may be a truncated
    prefix, not a complete document. Chunks remain in memory until joined,
    so total allocation grows with the result size. For an UploadFile, this
    reads the file already parsed by the framework, not the network stream.
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
