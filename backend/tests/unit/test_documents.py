# backend/tests/unit/test_documents.py

"""Unit tests for `read_document`.

This helper is what bounds an upload: it pulls the file in `CHUNK_SIZE` pieces
and stops one byte past the caller's limit. That overshoot byte is the point —
an oversized document is never assembled in memory in full, yet the caller's
own `len(data) > limit` check still has something to trip on.
"""

from __future__ import annotations

from app.lib.documents import CHUNK_SIZE, read_document


class FakeUpload:
    """An in-memory `AsyncByteReader` that records what it was asked for."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self.consumed = 0
        self.requested: list[int] = []

    async def read(self, size: int = -1, /) -> bytes:
        self.requested.append(size)
        end = len(self._data) if size < 0 else self.consumed + size
        chunk = self._data[self.consumed : end]
        self.consumed += len(chunk)
        return chunk


async def test_reads_a_document_below_the_limit_whole() -> None:
    upload = FakeUpload(b"a small document")

    data = await read_document(upload, limit=1024)

    assert data == b"a small document"


async def test_reads_a_document_exactly_at_the_limit_whole() -> None:
    # The boundary is inclusive: `limit` bytes is a legal document, so the
    # caller's `len(data) > limit` must not trip on it.
    upload = FakeUpload(b"x" * 64)

    data = await read_document(upload, limit=64)

    assert data == b"x" * 64


async def test_stops_one_byte_past_the_limit() -> None:
    upload = FakeUpload(b"x" * 10_000)

    data = await read_document(upload, limit=64)

    # Enough to fail the caller's check, and not a byte more read off the wire.
    assert len(data) == 65
    assert upload.consumed == 65


async def test_reads_in_chunk_sized_pieces() -> None:
    body = b"y" * (CHUNK_SIZE * 2 + 5)
    upload = FakeUpload(body)

    data = await read_document(upload, limit=len(body) * 2)

    assert data == body
    # Never a single unbounded read: peak allocation stays at one chunk.
    assert upload.requested
    assert all(0 < size <= CHUNK_SIZE for size in upload.requested)


async def test_reads_an_empty_document() -> None:
    upload = FakeUpload(b"")

    data = await read_document(upload, limit=1024)

    assert data == b""
