# backend/app/integrations/storage/errors.py

from __future__ import annotations


class DocumentStorageError(Exception):
    """Base class for document storage failures."""


class InvalidStorageKeyError(DocumentStorageError):
    """A storage key is malformed or would resolve outside the storage root."""

    def __init__(self, storage_key: str) -> None:
        super().__init__(f"Invalid storage key: {storage_key!r}")
        self.storage_key = storage_key


class DocumentNotFoundError(DocumentStorageError):
    """No stored document exists for the given storage key."""

    def __init__(self, storage_key: str) -> None:
        super().__init__(f"No document stored for key: {storage_key!r}")
        self.storage_key = storage_key


__all__ = [
    "DocumentNotFoundError",
    "DocumentStorageError",
    "InvalidStorageKeyError",
]
