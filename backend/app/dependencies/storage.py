# backend/app/dependencies/storage.py

from __future__ import annotations

from fastapi import Request

from app.integrations.storage import DocumentStorageClient


def get_document_storage(request: Request) -> DocumentStorageClient:
    return request.app.state.document_storage


__all__ = ["get_document_storage"]
