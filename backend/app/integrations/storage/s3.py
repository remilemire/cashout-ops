# backend/app/integrations/storage/s3.py

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from botocore.exceptions import ClientError

from .errors import DocumentNotFoundError
from .keys import validate_storage_key

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class S3DocumentStorageClient:
    """`DocumentStorageClient` backed by an S3 (or S3-compatible) bucket.

    boto3 is synchronous but its clients are thread-safe, so a single injected
    client is shared and each call is offloaded to a worker thread to keep the
    event loop free.

    Every key is validated (see `validate_storage_key`) before it is used as
    the object key, so a malformed or traversing key is rejected rather than
    addressing an unintended object.
    """

    def __init__(self, s3: S3Client, *, bucket: str) -> None:
        self._s3 = s3
        self._bucket = bucket

    async def read(self, storage_key: str) -> bytes:
        key = validate_storage_key(storage_key)

        def _read() -> bytes:
            response = self._s3.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()

        try:
            return await asyncio.to_thread(_read)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "NoSuchKey":
                raise DocumentNotFoundError(storage_key) from exc
            raise

    async def write(self, storage_key: str, data: bytes) -> None:
        key = validate_storage_key(storage_key)
        await asyncio.to_thread(
            self._s3.put_object, Bucket=self._bucket, Key=key, Body=data
        )

    async def delete(self, storage_key: str) -> None:
        key = validate_storage_key(storage_key)
        # S3 DeleteObject succeeds for a missing key, matching the local
        # client's `missing_ok=True` idempotent delete.
        await asyncio.to_thread(self._s3.delete_object, Bucket=self._bucket, Key=key)


__all__ = ["S3DocumentStorageClient"]
