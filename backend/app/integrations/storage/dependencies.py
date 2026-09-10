from __future__ import annotations

from fastapi import Request

from .client import DocumentStorageClient


def get_document_storage(request: Request) -> DocumentStorageClient:
    return request.app.state.document_storage


__all__ = ["get_document_storage"]
