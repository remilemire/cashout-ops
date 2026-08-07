# backend/app/integrations/storage/lifespan.py

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from app.core.config import settings

from .local import LocalDocumentStorageClient


@asynccontextmanager
async def storage_lifespan() -> AsyncGenerator[LocalDocumentStorageClient]:
    """Build the local document storage client; no teardown is required."""
    yield LocalDocumentStorageClient(settings.DOCUMENT_STORAGE_DIR)
