from __future__ import annotations

from typing import Protocol


class DocumentStorageClient(Protocol):
    """Resolves an application storage key to document content."""

    async def read(self, storage_key: str) -> bytes: ...


__all__ = ["DocumentStorageClient"]
