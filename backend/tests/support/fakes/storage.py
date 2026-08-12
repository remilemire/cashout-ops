# backend/tests/support/fakes/storage.py

from __future__ import annotations

from app.integrations.storage import (
    DocumentNotFoundError,
    DocumentStorageClient,
    validate_storage_key,
)


class FakeDocumentStorage(DocumentStorageClient):
    """In-memory `DocumentStorageClient`.

    Enforces the same key-containment rule as the real client
    (`validate_storage_key`) and raises the same errors, so a test exercising
    the storage boundary can't pass against the fake while failing against a
    real backend.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def read(self, storage_key: str) -> bytes:
        key = validate_storage_key(storage_key)
        try:
            return self.objects[key]
        except KeyError as exc:
            raise DocumentNotFoundError(key) from exc

    async def write(self, storage_key: str, data: bytes) -> None:
        self.objects[validate_storage_key(storage_key)] = data

    async def delete(self, storage_key: str) -> None:
        self.objects.pop(validate_storage_key(storage_key), None)


__all__ = ["FakeDocumentStorage"]
