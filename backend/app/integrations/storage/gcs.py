from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from google.api_core.exceptions import NotFound

from .errors import DocumentNotFoundError
from .keys import validate_storage_key

if TYPE_CHECKING:
    from google.cloud import storage as gcs


class GCSDocumentStorageClient:
    """`DocumentStorageClient` backed by a Google Cloud Storage bucket.

    google-cloud-storage is synchronous, and its own transfer manager shares
    one client across worker threads, so a single injected client is shared
    here too and each call is offloaded to a worker thread to keep the event
    loop free.

    Every key is validated (see `validate_storage_key`) before it is used as
    the object name, so a malformed or traversing key is rejected rather than
    addressing an unintended object.
    """

    def __init__(self, client: gcs.Client, *, bucket: str) -> None:
        # A bucket handle is local state; no request is made until a blob
        # method runs.
        self._bucket = client.bucket(bucket)

    async def read(self, storage_key: str) -> bytes:
        key = validate_storage_key(storage_key)
        try:
            return await asyncio.to_thread(self._bucket.blob(key).download_as_bytes)
        except NotFound as exc:
            raise DocumentNotFoundError(storage_key) from exc

    async def write(self, storage_key: str, data: bytes) -> None:
        key = validate_storage_key(storage_key)
        # upload_from_string defaults the object's content type to text/plain;
        # octet-stream keeps the stored bytes opaque, as S3's put_object does.
        await asyncio.to_thread(
            self._bucket.blob(key).upload_from_string,
            data,
            content_type="application/octet-stream",
        )

    async def delete(self, storage_key: str) -> None:
        key = validate_storage_key(storage_key)
        # GCS rejects deleting a missing object; swallowing that matches the
        # local client's `missing_ok=True` idempotent delete.
        try:
            await asyncio.to_thread(self._bucket.blob(key).delete)
        except NotFound:
            pass


__all__ = ["GCSDocumentStorageClient"]
