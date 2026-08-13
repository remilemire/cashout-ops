# backend/app/integrations/storage/lifespan.py

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import boto3

from app.core.config import settings
from app.core.providers import StorageProvider

from .client import DocumentStorageClient
from .local import LocalDocumentStorageClient
from .s3 import S3DocumentStorageClient

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


@asynccontextmanager
async def storage_lifespan() -> AsyncGenerator[DocumentStorageClient]:
    """Build the configured document storage client; no teardown is required."""
    yield _build_document_storage()


def _build_document_storage() -> DocumentStorageClient:
    """Select the configured storage client.

    Settings already rejects a provider whose own configuration is missing, so
    the guards below narrow those optional fields for the type checker rather
    than enforcing the requirement themselves.
    """
    if settings.storage.PROVIDER is StorageProvider.S3:
        if not settings.storage.S3_BUCKET or not settings.storage.S3_REGION:
            raise RuntimeError(
                "S3_BUCKET and S3_REGION are required when STORAGE_PROVIDER is S3."
            )
        # AWS credentials intentionally come from the standard AWS chain (env
        # vars, profile, instance role) rather than Settings, so every
        # deployment style works without modeling provider secrets here.
        # boto3-stubs types boto3.client with one overload per AWS service;
        # only the s3 stubs are installed, so the others return Unknown and
        # the symbol reads as partially unknown. The "s3" overload itself
        # resolves, as the S3Client annotation verifies.
        s3: S3Client = boto3.client(  # pyright: ignore[reportUnknownMemberType]
            "s3",
            region_name=settings.storage.S3_REGION,
            # Unset (None) is boto3's own default, which resolves the AWS
            # endpoint for the region; a value targets an S3-compatible store.
            endpoint_url=settings.storage.S3_ENDPOINT_URL,
        )
        return S3DocumentStorageClient(s3, bucket=settings.storage.S3_BUCKET)
    if settings.storage.LOCAL_DIR is None:
        raise RuntimeError(
            "STORAGE_LOCAL_DIR is required when STORAGE_PROVIDER is LOCAL."
        )
    return LocalDocumentStorageClient(settings.storage.LOCAL_DIR)
