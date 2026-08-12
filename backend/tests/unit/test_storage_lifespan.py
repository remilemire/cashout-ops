# backend/tests/unit/test_storage_lifespan.py

"""The storage lifespan hands out the client selected by configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings
from app.core.providers import StorageProvider
from app.integrations.storage import (
    LocalDocumentStorageClient,
    S3DocumentStorageClient,
)
from app.integrations.storage.lifespan import storage_lifespan


async def test_local_provider_builds_the_local_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PROVIDER", StorageProvider.LOCAL)
    monkeypatch.setattr(settings, "LOCAL_STORAGE_DIR", Path("storage/documents"))

    async with storage_lifespan() as storage:
        assert isinstance(storage, LocalDocumentStorageClient)


async def test_s3_provider_builds_the_s3_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PROVIDER", StorageProvider.S3)
    monkeypatch.setattr(settings, "S3_BUCKET", "test-bucket")
    # A concrete region keeps boto3 client construction independent of any AWS
    # config present (or absent) on the host running the tests.
    monkeypatch.setattr(settings, "S3_REGION", "us-east-1")

    async with storage_lifespan() as storage:
        assert isinstance(storage, S3DocumentStorageClient)


# Settings rejects these combinations at load, so the lifespan can only reach
# them when an already-built settings object is mutated. The guards still hold,
# which is what keeps the optional fields safe to unwrap.
async def test_s3_provider_without_bucket_fails_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PROVIDER", StorageProvider.S3)
    monkeypatch.setattr(settings, "S3_BUCKET", None)
    monkeypatch.setattr(settings, "S3_REGION", "us-east-1")

    with pytest.raises(RuntimeError, match="S3_BUCKET"):
        async with storage_lifespan():
            pass


async def test_s3_provider_without_region_fails_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PROVIDER", StorageProvider.S3)
    monkeypatch.setattr(settings, "S3_BUCKET", "test-bucket")
    monkeypatch.setattr(settings, "S3_REGION", None)

    with pytest.raises(RuntimeError, match="S3_REGION"):
        async with storage_lifespan():
            pass


async def test_local_provider_without_directory_fails_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PROVIDER", StorageProvider.LOCAL)
    monkeypatch.setattr(settings, "LOCAL_STORAGE_DIR", None)

    with pytest.raises(RuntimeError, match="LOCAL_STORAGE_DIR"):
        async with storage_lifespan():
            pass
