# backend/tests/unit/test_storage_lifespan.py

"""The storage lifespan hands out the client selected by configuration."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.storage import StorageProvider
from app.integrations.storage import (
    LocalDocumentStorageClient,
    S3DocumentStorageClient,
)
from app.integrations.storage.lifespan import storage_lifespan


async def test_local_provider_builds_the_local_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PROVIDER", StorageProvider.LOCAL)

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
    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", None)

    async with storage_lifespan() as storage:
        assert isinstance(storage, S3DocumentStorageClient)


async def test_s3_provider_without_bucket_fails_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_PROVIDER", StorageProvider.S3)
    monkeypatch.setattr(settings, "S3_BUCKET", None)

    with pytest.raises(RuntimeError, match="S3_BUCKET"):
        async with storage_lifespan():
            pass
