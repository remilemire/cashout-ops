# backend/tests/unit/test_s3_storage.py

"""Unit tests for `S3DocumentStorageClient`.

These pin the same security contract as the local client: a `storage_key` is
an opaque application key and must never address an object it does not own.
An escaping key (parent traversal, an absolute path, or an escape embedded
after a valid-looking prefix) is rejected with `InvalidStorageKeyError`
before any S3 call is made, and a missing — but otherwise valid — key reads
as `DocumentNotFoundError` rather than a leaked provider error. Any other
provider failure propagates untranslated.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any, cast

import pytest
from botocore.exceptions import ClientError

from app.integrations.storage.errors import (
    DocumentNotFoundError,
    InvalidStorageKeyError,
)
from app.integrations.storage.s3 import S3DocumentStorageClient

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

# Each key reaches outside the storage namespace by a different escape
# technique, so every read/write/delete test covers all three.
_ESCAPING_KEYS = ["../escape.txt", "/absolute/escape.txt", "nested/../../escape.txt"]


def _client_error(code: str, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


class _FakeS3:
    """In-memory stand-in for the S3 client surface the storage client uses."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.calls: list[str] = []
        self.get_error: ClientError | None = None

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.calls.append("get_object")
        if self.get_error is not None:
            raise self.get_error
        try:
            data = self.objects[(Bucket, Key)]
        except KeyError:
            raise _client_error("NoSuchKey", "GetObject") from None
        return {"Body": io.BytesIO(data)}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> dict[str, Any]:
        self.calls.append("put_object")
        self.objects[(Bucket, Key)] = Body
        return {}

    def delete_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        # Like S3 DeleteObject, succeeds whether or not the key exists.
        self.calls.append("delete_object")
        self.objects.pop((Bucket, Key), None)
        return {}


def _client() -> tuple[S3DocumentStorageClient, _FakeS3]:
    fake = _FakeS3()
    return S3DocumentStorageClient(cast("S3Client", fake), bucket="test-bucket"), fake


@pytest.mark.parametrize("key", _ESCAPING_KEYS)
async def test_read_rejects_escaping_key_before_any_s3_call(key: str) -> None:
    client, fake = _client()

    with pytest.raises(InvalidStorageKeyError):
        await client.read(key)
    assert fake.calls == []


@pytest.mark.parametrize("key", _ESCAPING_KEYS)
async def test_write_rejects_escaping_key_before_any_s3_call(key: str) -> None:
    client, fake = _client()

    with pytest.raises(InvalidStorageKeyError):
        await client.write(key, b"attacker-controlled")
    assert fake.calls == []


@pytest.mark.parametrize("key", _ESCAPING_KEYS)
async def test_delete_rejects_escaping_key_before_any_s3_call(key: str) -> None:
    client, fake = _client()

    with pytest.raises(InvalidStorageKeyError):
        await client.delete(key)
    assert fake.calls == []


async def test_read_missing_key_raises_not_found() -> None:
    client, _ = _client()

    # A well-formed key with nothing stored behind it is a not-found; the
    # provider error is chained for logs, not exposed as the raise.
    with pytest.raises(DocumentNotFoundError) as excinfo:
        await client.read("cashout/2024/missing.pdf")
    assert isinstance(excinfo.value.__cause__, ClientError)


async def test_read_propagates_other_provider_errors() -> None:
    client, fake = _client()
    fake.get_error = _client_error("AccessDenied", "GetObject")

    # Only a missing object is translated; an infrastructure failure must not
    # masquerade as a not-found.
    with pytest.raises(ClientError):
        await client.read("cashout/2024/doc.pdf")


async def test_round_trip_against_the_bucket() -> None:
    """Baseline: legitimate nested keys work, so the escape tests above are
    pinning containment specifically — not just 'everything raises'."""
    client, fake = _client()
    key = "cashout/2024/doc.pdf"

    await client.write(key, b"hello")
    assert fake.objects == {("test-bucket", key): b"hello"}  # right bucket + key

    assert await client.read(key) == b"hello"

    await client.delete(key)
    assert fake.objects == {}


async def test_delete_missing_key_does_not_raise() -> None:
    client, _ = _client()

    await client.delete("cashout/2024/missing.pdf")
