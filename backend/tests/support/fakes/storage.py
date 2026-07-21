# backend/tests/support/fakes/storage.py

from __future__ import annotations


class FakeDocumentStorage:
    """In-memory `DocumentStorageClient`."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def read(self, storage_key: str) -> bytes:
        return self.objects[storage_key]

    async def write(self, storage_key: str, data: bytes) -> None:
        self.objects[storage_key] = data

    async def delete(self, storage_key: str) -> None:
        self.objects.pop(storage_key, None)
