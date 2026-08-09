# backend/app/integrations/storage/local.py

from __future__ import annotations

import asyncio
from pathlib import Path

from .errors import DocumentNotFoundError
from .keys import validate_storage_key


class LocalDocumentStorageClient:
    """`DocumentStorageClient` backed by a local directory.

    Suitable for development and single-instance deployments; the directory is
    not durable on ephemeral hosts, so swap in an object-store client before
    relying on it in production.

    Every key is validated (see `validate_storage_key`) before it is joined
    onto the root, so a malformed or traversing key is rejected rather than
    escaping the storage directory.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    async def read(self, storage_key: str) -> bytes:
        path = self._path(storage_key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise DocumentNotFoundError(storage_key) from exc

    async def write(self, storage_key: str, data: bytes) -> None:
        path = self._path(storage_key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(_write)

    async def delete(self, storage_key: str) -> None:
        path = self._path(storage_key)
        await asyncio.to_thread(path.unlink, missing_ok=True)

    def _path(self, storage_key: str) -> Path:
        return self._root / validate_storage_key(storage_key)


__all__ = ["LocalDocumentStorageClient"]
