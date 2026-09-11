"""Unit tests for `GCSDocumentStorageClient`.

These pin the same security contract as the local and S3 clients: a
`storage_key` is an opaque application key and must never address an object
it does not own. An escaping key (parent traversal, an absolute path, or an
escape embedded after a valid-looking prefix) is rejected with
`InvalidStorageKeyError` before any GCS call is made, and a missing — but
otherwise valid — key reads as `DocumentNotFoundError` rather than a leaked
provider error. Any other provider failure propagates untranslated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from google.api_core.exceptions import Forbidden, GoogleAPICallError, NotFound

from app.integrations.storage.errors import (
    DocumentNotFoundError,
    InvalidStorageKeyError,
)
from app.integrations.storage.gcs import GCSDocumentStorageClient

if TYPE_CHECKING:
    from google.cloud import storage as gcs

# Each key reaches outside the storage namespace by a different escape
# technique, so every read/write/delete test covers all three.
_ESCAPING_KEYS = ["../escape.txt", "/absolute/escape.txt", "nested/../../escape.txt"]


class _FakeGCS:
    """In-memory stand-in for the GCS client surface the storage client uses.

    The library hands out bucket and blob handles that share one client; the
    fake handles below share this object's state the same way.
    """

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.content_types: dict[tuple[str, str], str] = {}
        self.calls: list[str] = []
        self.get_error: GoogleAPICallError | None = None

    def bucket(self, bucket_name: str) -> _FakeBucket:
        return _FakeBucket(self, bucket_name)


class _FakeBucket:
    def __init__(self, client: _FakeGCS, name: str) -> None:
        self._client = client
        self.name = name

    def blob(self, blob_name: str) -> _FakeBlob:
        return _FakeBlob(self._client, (self.name, blob_name))


class _FakeBlob:
    def __init__(self, client: _FakeGCS, key: tuple[str, str]) -> None:
        self._client = client
        self._key = key

    def download_as_bytes(self) -> bytes:
        self._client.calls.append("download_as_bytes")
        if self._client.get_error is not None:
            raise self._client.get_error
        try:
            return self._client.objects[self._key]
        except KeyError:
            raise NotFound("No such object") from None

    def upload_from_string(self, data: bytes, content_type: str = "text/plain") -> None:
        self._client.calls.append("upload_from_string")
        self._client.objects[self._key] = data
        self._client.content_types[self._key] = content_type

    def delete(self) -> None:
        # Unlike S3 DeleteObject, GCS rejects deleting a missing object; the
        # storage client is what makes delete idempotent.
        self._client.calls.append("delete")
        try:
            del self._client.objects[self._key]
        except KeyError:
            raise NotFound("No such object") from None
        self._client.content_types.pop(self._key, None)


def _client() -> tuple[GCSDocumentStorageClient, _FakeGCS]:
    fake = _FakeGCS()
    client = GCSDocumentStorageClient(cast("gcs.Client", fake), bucket="test-bucket")
    return client, fake


@pytest.mark.parametrize("key", _ESCAPING_KEYS)
async def test_read_rejects_escaping_key_before_any_gcs_call(key: str) -> None:
    client, fake = _client()

    with pytest.raises(InvalidStorageKeyError):
        await client.read(key)
    assert fake.calls == []


@pytest.mark.parametrize("key", _ESCAPING_KEYS)
async def test_write_rejects_escaping_key_before_any_gcs_call(key: str) -> None:
    client, fake = _client()

    with pytest.raises(InvalidStorageKeyError):
        await client.write(key, b"attacker-controlled")
    assert fake.calls == []


@pytest.mark.parametrize("key", _ESCAPING_KEYS)
async def test_delete_rejects_escaping_key_before_any_gcs_call(key: str) -> None:
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
    assert isinstance(excinfo.value.__cause__, NotFound)


async def test_read_propagates_other_provider_errors() -> None:
    client, fake = _client()
    fake.get_error = Forbidden("Access denied")

    # Only a missing object is translated; an infrastructure failure must not
    # masquerade as a not-found.
    with pytest.raises(Forbidden):
        await client.read("cashout/2024/doc.pdf")


async def test_round_trip_against_the_bucket() -> None:
    """Baseline: legitimate nested keys work, so the escape tests above are
    pinning containment specifically — not just 'everything raises'."""
    client, fake = _client()
    key = "cashout/2024/doc.pdf"

    await client.write(key, b"hello")
    assert fake.objects == {("test-bucket", key): b"hello"}  # right bucket + key
    # Stored as opaque bytes, not the library's text/plain default.
    assert fake.content_types == {("test-bucket", key): "application/octet-stream"}

    assert await client.read(key) == b"hello"

    await client.delete(key)
    assert fake.objects == {}


async def test_delete_missing_key_does_not_raise() -> None:
    client, fake = _client()

    # The fake raises NotFound like GCS does; the client swallows it.
    await client.delete("cashout/2024/missing.pdf")
    assert fake.calls == ["delete"]
