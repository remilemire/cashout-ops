# backend/tests/unit/test_local_storage.py

"""Unit tests for `LocalDocumentStorageClient`.

These pin the security contract the client upholds: a `storage_key` is an
opaque application key and must never reach a file outside the configured
storage root. An escaping key (parent traversal, an absolute path, or an
escape embedded after a valid-looking prefix) is rejected with
`InvalidStorageKeyError` before any filesystem access, and a missing — but
otherwise valid — key reads as `DocumentNotFoundError`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.integrations.storage.errors import (
    DocumentNotFoundError,
    InvalidStorageKeyError,
)
from app.integrations.storage.local import LocalDocumentStorageClient

# Every kind resolves to `outside` (one level above the storage root), reached
# by a different escape technique, so each read/write/delete test covers all
# three against the same target file.
_ESCAPE_KINDS = ["parent_traversal", "absolute_path", "embedded_traversal"]


def _escaping_key(outside: Path, kind: str) -> str:
    if kind == "parent_traversal":
        return f"../{outside.name}"  # climbs out of the root
    if kind == "absolute_path":
        return str(outside)  # absolute key discards the root entirely
    if kind == "embedded_traversal":
        return f"nested/../../{outside.name}"  # escapes after a valid-looking prefix
    raise AssertionError(f"unhandled escape kind: {kind}")


@pytest.mark.parametrize("kind", _ESCAPE_KINDS)
async def test_read_cannot_escape_storage_root(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"top-secret")

    client = LocalDocumentStorageClient(root)
    key = _escaping_key(outside, kind)

    # Rejected outright — never used to read an out-of-root file.
    with pytest.raises(InvalidStorageKeyError):
        await client.read(key)


@pytest.mark.parametrize("kind", _ESCAPE_KINDS)
async def test_write_cannot_escape_storage_root(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    outside = tmp_path / "planted.txt"

    client = LocalDocumentStorageClient(root)
    key = _escaping_key(outside, kind)

    with pytest.raises(InvalidStorageKeyError):
        await client.write(key, b"attacker-controlled")
    # The security invariant, independent of how the client signals failure:
    # no bytes may be planted outside the root.
    assert not outside.exists()


@pytest.mark.parametrize("kind", _ESCAPE_KINDS)
async def test_delete_cannot_escape_storage_root(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    outside = tmp_path / "victim.txt"
    outside.write_bytes(b"keep me")

    client = LocalDocumentStorageClient(root)
    key = _escaping_key(outside, kind)

    with pytest.raises(InvalidStorageKeyError):
        await client.delete(key)
    # Deletion must not reach outside the root.
    assert outside.exists()


async def test_read_missing_key_raises_not_found(tmp_path: Path) -> None:
    root = tmp_path / "documents"
    client = LocalDocumentStorageClient(root)

    # A well-formed key with nothing stored behind it is a not-found, not a
    # leaked raw OSError.
    with pytest.raises(DocumentNotFoundError):
        await client.read("cashout/2024/missing.pdf")


async def test_round_trip_within_root(tmp_path: Path) -> None:
    """Baseline: legitimate nested keys still work, so the escape tests above
    are pinning containment specifically — not just 'everything raises'."""
    root = tmp_path / "documents"
    client = LocalDocumentStorageClient(root)
    key = "cashout/2024/doc.pdf"

    await client.write(key, b"hello")
    assert (root / key).read_bytes() == b"hello"  # landed inside the root
    assert await client.read(key) == b"hello"

    await client.delete(key)
    assert not (root / key).exists()
