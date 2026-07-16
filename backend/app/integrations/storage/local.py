from __future__ import annotations

import asyncio
from pathlib import Path


class LocalDocumentStorageClient:
    """`DocumentStorageClient` backed by a local directory.

    Suitable for development and single-instance deployments; the directory is
    not durable on ephemeral hosts, so swap in an object-store client before
    relying on it in production.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    async def read(self, storage_key: str) -> bytes:
        return await asyncio.to_thread((self._root / storage_key).read_bytes)

    async def write(self, storage_key: str, data: bytes) -> None:
        def _write() -> None:
            path = self._root / storage_key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(_write)


__all__ = ["LocalDocumentStorageClient"]
