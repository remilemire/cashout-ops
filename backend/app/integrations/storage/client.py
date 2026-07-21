# backend/app/integrations/storage/client.py

from __future__ import annotations

from typing import Protocol


class DocumentStorageClient(Protocol):
    """Resolves an application storage key to document content."""

    async def read(self, storage_key: str) -> bytes: ...

    async def write(self, storage_key: str, data: bytes) -> None: ...

    async def delete(self, storage_key: str) -> None: ...


__all__ = ["DocumentStorageClient"]
