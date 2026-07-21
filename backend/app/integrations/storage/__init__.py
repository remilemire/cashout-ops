# backend/app/integrations/storage/__init__.py

from __future__ import annotations

from .client import DocumentStorageClient
from .local import LocalDocumentStorageClient

__all__ = ["DocumentStorageClient", "LocalDocumentStorageClient"]
